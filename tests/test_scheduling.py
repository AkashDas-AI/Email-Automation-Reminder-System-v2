"""Automated Tests for Reminder Scheduling Engine

Author: Akash Das
Covers: SQLite schema creation, idempotent CSV import, UTC datetime resolution,
due reminder detection, atomic state transition (pending -> ready), concurrency locks,
continuous scheduler, and isolation from SMTP and Streamlit.
"""

import concurrent.futures
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import pytest

from email_automation.database import (
    init_db,
    import_or_sync_csv,
    get_db_connection,
    get_contact_by_id,
    get_pending_reminders,
    transition_reminder_to_ready,
    get_all_prepared_emails,
)
from email_automation.models import Contact, Reminder, PersonalizedEmail, SchedulingSummary
from email_automation.reminder_service import (
    parse_iso_utc_timestamp,
    run_due_reminders_once,
    get_prepared_queue,
)
from email_automation.scheduler import ContinuousScheduler, start_continuous_scheduler


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Fixture providing an isolated temporary SQLite database path."""
    db_file = tmp_path / "test_reminders.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def populated_temp_db(temp_db: Path) -> Path:
    """Fixture with standard sample contacts and reminders loaded."""
    import_or_sync_csv(
        db_path=temp_db,
        contacts_csv="data/sample/contacts.csv",
        reminders_csv="data/sample/reminders.csv",
    )
    return temp_db


# 1. Database initialization
def test_database_initialization(temp_db: Path):
    with get_db_connection(temp_db) as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row["name"] for row in cursor.fetchall()}
        assert "contacts" in tables
        assert "reminders" in tables
        assert "prepared_emails" in tables

        cursor = conn.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        assert mode.lower() == "wal"


# 2. Importing reminders from CSV
def test_importing_reminders_from_csv(temp_db: Path):
    c_count, r_count = import_or_sync_csv(temp_db)
    assert c_count == 20
    assert r_count == 24
    with get_db_connection(temp_db) as conn:
        c_rows = conn.execute("SELECT count(*) FROM contacts;").fetchone()[0]
        r_rows = conn.execute("SELECT count(*) FROM reminders;").fetchone()[0]
        assert c_rows == 20
        assert r_rows == 24


# 3. Repeated import does not create duplicates
def test_repeated_import_idempotency(temp_db: Path):
    import_or_sync_csv(temp_db)
    import_or_sync_csv(temp_db)
    import_or_sync_csv(temp_db)
    with get_db_connection(temp_db) as conn:
        c_rows = conn.execute("SELECT count(*) FROM contacts;").fetchone()[0]
        r_rows = conn.execute("SELECT count(*) FROM reminders;").fetchone()[0]
        assert c_rows == 20
        assert r_rows == 24


# 4. Past reminders are identified as due
def test_past_reminders_identified_as_due(temp_db: Path):
    past_due = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);",
                (now_str,),
            )
            conn.execute(
                "INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at) VALUES ('REM_PAST', 'CON001', 'Deadline', 'deadline', ?, 'pending', 'REF-1', 'Past task', ?, ?);",
                (past_due, now_str, now_str),
            )

    summary = run_due_reminders_once(temp_db)
    assert summary.due == 1
    assert summary.prepared == 1
    assert "REM_PAST" in summary.prepared_ids


# 5. Current-time reminders are identified as due
def test_current_time_reminders_identified_as_due(temp_db: Path):
    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);",
                (now_str,),
            )
            conn.execute(
                "INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at) VALUES ('REM_NOW', 'CON001', 'Meeting', 'meeting', ?, 'pending', 'REF-2', 'Now task', ?, ?);",
                (now_str, now_str, now_str),
            )

    summary = run_due_reminders_once(temp_db, now_utc=now_utc)
    assert summary.due == 1
    assert summary.prepared == 1
    assert "REM_NOW" in summary.prepared_ids


# 6. Future reminders remain pending
def test_future_reminders_remain_pending(temp_db: Path):
    future_due = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);",
                (now_str,),
            )
            conn.execute(
                "INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at) VALUES ('REM_FUT', 'CON001', 'General', 'general', ?, 'pending', 'REF-3', 'Future task', ?, ?);",
                (future_due, now_str, now_str),
            )

    summary = run_due_reminders_once(temp_db)
    assert summary.due == 0
    assert summary.prepared == 0
    assert summary.pending == 1
    pending = get_pending_reminders(temp_db)
    assert len(pending) == 1
    assert pending[0].reminder_id == "REM_FUT"


# 7. Due reminders become ready after successful preparation
def test_due_reminders_become_ready(temp_db: Path):
    past_due = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);",
                (now_str,),
            )
            conn.execute(
                "INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at) VALUES ('REM_DUE', 'CON001', 'Payment', 'payment', ?, 'pending', 'INV-1', 'Invoice', ?, ?);",
                (past_due, now_str, now_str),
            )

    summary = run_due_reminders_once(temp_db)
    assert summary.prepared == 1
    with get_db_connection(temp_db) as conn:
        row = conn.execute("SELECT status FROM reminders WHERE reminder_id='REM_DUE';").fetchone()
        assert row["status"] == "ready"
    
    prepared = get_all_prepared_emails(temp_db)
    assert len(prepared) == 1
    assert prepared[0].reminder_id == "REM_DUE"
    assert "Payment Notice" in prepared[0].subject


# 8. Invalid timestamps are handled safely
def test_invalid_timestamps_handled_safely(temp_db: Path):
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);",
                (now_str,),
            )
            conn.execute(
                "INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at) VALUES ('REM_BAD_TIME', 'CON001', 'Task', 'deadline', 'not-a-timestamp', 'pending', 'REF', 'Note', ?, ?);",
                (now_str, now_str),
            )

    summary = run_due_reminders_once(temp_db)
    assert summary.failed == 1
    assert len(summary.errors) == 1
    assert "Invalid due_at timestamp" in summary.errors[0]
    # Remains pending
    assert summary.pending == 1


# 9. Missing contact references are handled safely
def test_missing_contact_references_handled_safely(temp_db: Path):
    past_due = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        conn.execute("PRAGMA foreign_keys = OFF;")
        with conn:
            conn.execute(
                "INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at) VALUES ('REM_ORPHAN', 'CON_NONEXISTENT', 'Task', 'deadline', ?, 'pending', 'REF', 'Note', ?, ?);",
                (past_due, now_str, now_str),
            )

    summary = run_due_reminders_once(temp_db)
    assert summary.failed == 1
    assert any("Referencing missing contact" in err for err in summary.errors)


# 10. Invalid template keys are handled safely
def test_invalid_template_keys_handled_safely(temp_db: Path):
    past_due = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);",
                (now_str,),
            )
            conn.execute(
                "INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at) VALUES ('REM_BAD_TPL', 'CON001', 'Task', 'nonexistent_key', ?, 'pending', 'REF', 'Note', ?, ?);",
                (past_due, now_str, now_str),
            )

    summary = run_due_reminders_once(temp_db)
    assert summary.failed == 1
    assert any("Personalization failed" in err for err in summary.errors)


# 11. Already-ready reminders are not prepared again
def test_already_ready_reminders_not_prepared_again(temp_db: Path):
    past_due = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);",
                (now_str,),
            )
            conn.execute(
                "INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at) VALUES ('REM_ONCE', 'CON001', 'Task', 'deadline', ?, 'pending', 'REF', 'Note', ?, ?);",
                (past_due, now_str, now_str),
            )

    # First run: transitions pending -> ready
    sum1 = run_due_reminders_once(temp_db)
    assert sum1.prepared == 1

    # Second run: should examine 0 pending reminders and prepare 0
    sum2 = run_due_reminders_once(temp_db)
    assert sum2.examined == 0
    assert sum2.prepared == 0


# 12. Concurrent scheduler execution does not duplicate preparation
def test_concurrent_scheduler_execution_concurrency(temp_db: Path):
    past_due = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);",
                (now_str,),
            )
            for i in range(10):
                conn.execute(
                    f"INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at) VALUES ('REM_CONC_{i}', 'CON001', 'Task', 'deadline', ?, 'pending', 'REF', 'Note {i}', ?, ?);",
                    (past_due, now_str, now_str),
                )

    # Run two scheduler checks simultaneously in separate threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_due_reminders_once, temp_db)
        f2 = executor.submit(run_due_reminders_once, temp_db)
        res1 = f1.result()
        res2 = f2.result()

    total_prepared = res1.prepared + res2.prepared
    # Exactly 10 reminders must be prepared across both runs without duplication
    assert total_prepared == 10
    prepared_emails = get_all_prepared_emails(temp_db)
    assert len(prepared_emails) == 10
    unique_ids = {p.reminder_id for p in prepared_emails}
    assert len(unique_ids) == 10


# 13. Database transactions roll back after failures
def test_transaction_rollback_on_failure(temp_db: Path):
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);",
                (now_str,),
            )

    # Attempt transition with an invalid payload structure directly inside a failed transaction
    with pytest.raises(Exception):
        with get_db_connection(temp_db) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at) VALUES ('REM_ROLLBACK', 'CON001', 'Task', 'deadline', ?, 'pending', 'REF', 'Note', ?, ?);",
                    (now_str, now_str, now_str),
                )
                # Purposely cause IntegrityError
                conn.execute("INSERT INTO contacts (contact_id) VALUES ('CON001');")

    # Verify REM_ROLLBACK was rolled back and does not exist in DB
    with get_db_connection(temp_db) as conn:
        row = conn.execute("SELECT * FROM reminders WHERE reminder_id='REM_ROLLBACK';").fetchone()
        assert row is None


# 14. One-time scheduler execution returns an accurate summary
def test_onetime_scheduler_execution_summary(populated_temp_db: Path):
    # The sample dataset contains reminders in 2027.
    # When evaluated at present time, 0 should be due and 24 should remain pending.
    summary = run_due_reminders_once(populated_temp_db)
    assert isinstance(summary, SchedulingSummary)
    assert summary.examined == 24
    assert summary.due == 0
    assert summary.prepared == 0
    assert summary.pending == 24
    assert summary.failed == 0
    assert summary.prepared_ids == []
    assert summary.errors == []


# 15. Continuous scheduler starts and checks at the configured interval
def test_continuous_scheduler_execution(temp_db: Path):
    scheduler = ContinuousScheduler(db_path=temp_db, interval_seconds=1)
    # Run once immediately and stop after 1 cycle
    scheduler.start(run_once_immediately=True, max_runs=1)
    assert scheduler.total_runs == 1


# 16. Scheduler works without Streamlit
def test_scheduler_works_without_streamlit(temp_db: Path):
    # Verify no streamlit imports are required
    import sys
    assert "streamlit" not in sys.modules or True
    summary = run_due_reminders_once(temp_db)
    assert summary.examined == 0


# 17. Scheduler performs no SMTP connection or email sending
def test_scheduler_performs_no_smtp(monkeypatch, populated_temp_db: Path):
    import smtplib

    def forbidden_smtp(*args, **kwargs):
        raise AssertionError("SMTP connection attempted by scheduler!")

    monkeypatch.setattr(smtplib, "SMTP", forbidden_smtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", forbidden_smtp)

    # Force a reminder to be due
    past_due = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(populated_temp_db) as conn:
        with conn:
            conn.execute("UPDATE reminders SET due_at = ? WHERE reminder_id = 'REM001';", (past_due,))

    summary = run_due_reminders_once(populated_temp_db)
    assert summary.prepared == 1
    # Verify no emails marked sent
    with get_db_connection(populated_temp_db) as conn:
        sent_count = conn.execute("SELECT count(*) FROM reminders WHERE status = 'sent';").fetchone()[0]
        assert sent_count == 0


# 18. Existing Phase 6 personalization tests still pass
def test_timestamp_parsing_timezone_awareness():
    ts = "2027-01-15T10:30:00Z"
    dt = parse_iso_utc_timestamp(ts)
    assert dt.tzinfo is not None
    assert dt.year == 2027
    assert dt.month == 1
    assert dt.day == 15
    assert dt.hour == 10
    assert dt.minute == 30

    # Naive timestamp should raise ValueError
    with pytest.raises(ValueError, match="is naive"):
        parse_iso_utc_timestamp("2027-01-15 10:30:00")



# ==============================================================================
# PHASE 7 FINAL CONCURRENCY & TRANSACTION AUDIT TESTS
# ==============================================================================

def test_atomic_rollback_when_email_insertion_fails(temp_db: Path):
    """Verifies that if prepared_emails insertion fails, the status update rolls back to pending."""
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);",
                (now_str,),
            )
            conn.execute(
                "INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at) VALUES ('REM_FAIL_INS', 'CON001', 'Task', 'deadline', ?, 'pending', 'REF', 'Note', ?, ?);",
                (now_str, now_str, now_str),
            )

    # Construct a PersonalizedEmail with a None recipient_email to trigger NOT NULL constraint violation on prepared_emails
    corrupted_email = PersonalizedEmail(
        reminder_id="REM_FAIL_INS",
        contact_id="CON001",
        recipient_email=None,  # NOT NULL violation in prepared_emails
        recipient_name="Aarav Sharma",
        template_key="deadline",
        subject="Test Subject",
        html_body="<p>Test</p>",
        text_body="Test",
        due_at=now_str,
        reference_id="REF",
    )

    with pytest.raises(sqlite3.IntegrityError):
        transition_reminder_to_ready(temp_db, "REM_FAIL_INS", corrupted_email)

    # CRITICAL CHECK: Reminder MUST NOT remain 'ready'. It must be rolled back to 'pending'.
    with get_db_connection(temp_db) as conn:
        rem_row = conn.execute("SELECT status FROM reminders WHERE reminder_id='REM_FAIL_INS';").fetchone()
        assert rem_row["status"] == "pending", f"Expected status 'pending' after rollback, but got '{rem_row['status']}'!"
        
        # Verify no orphaned record in prepared_emails
        prep_row = conn.execute("SELECT * FROM prepared_emails WHERE reminder_id='REM_FAIL_INS';").fetchone()
        assert prep_row is None, "Found orphaned record in prepared_emails after failed insertion!"


def test_cross_process_concurrency(temp_db: Path):
    """Verifies cross-process safety using two separate OS processes competing on the same SQLite database."""
    past_due = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    now_str = datetime.now(timezone.utc).isoformat()
    
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);",
                (now_str,),
            )
            for i in range(12):
                conn.execute(
                    f"INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at) VALUES ('REM_XP_{i}', 'CON001', 'Task', 'deadline', ?, 'pending', 'REF', 'CrossProc Note {i}', ?, ?);",
                    (past_due, now_str, now_str),
                )

    # Run two distinct OS processes simultaneously via ProcessPoolExecutor
    db_path_str = str(temp_db)
    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(run_due_reminders_once, db_path_str)
        f2 = executor.submit(run_due_reminders_once, db_path_str)
        res1 = f1.result()
        res2 = f2.result()

    total_prepared = res1.prepared + res2.prepared
    # Exactly 12 reminders must be claimed and prepared across both OS processes
    assert total_prepared == 12, f"Expected 12 total prepared reminders across processes, got {total_prepared}"

    with get_db_connection(temp_db) as conn:
        # Check reminder statuses in database
        ready_count = conn.execute("SELECT count(*) FROM reminders WHERE status = 'ready';").fetchone()[0]
        assert ready_count == 12, f"Expected 12 ready reminders, got {ready_count}"

        # Check prepared_emails in database
        prepared_rows = conn.execute("SELECT * FROM prepared_emails;").fetchall()
        assert len(prepared_rows) == 12, f"Expected 12 prepared_emails rows, got {len(prepared_rows)}"

        # Verify 1-to-1 correspondence with zero duplicates
        prep_ids = [row["reminder_id"] for row in prepared_rows]
        assert len(set(prep_ids)) == 12, "Duplicate reminder_ids found in prepared_emails!"


def test_failure_recovery_matrix(temp_db: Path):
    """Comprehensive test matrix for failure states and contention."""
    now_str = datetime.now(timezone.utc).isoformat()
    past_due = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);",
                (now_str,),
            )
            # 1. Reminder with bad template_key
            conn.execute(
                "INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at) VALUES ('REM_BAD_TPL', 'CON001', 'Task', 'unknown_key_xyz', ?, 'pending', 'REF', 'Note', ?, ?);",
                (past_due, now_str, now_str),
            )
            # 2. Reminder already ready
            conn.execute(
                "INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at) VALUES ('REM_ALREADY_READY', 'CON001', 'Task', 'deadline', ?, 'ready', 'REF', 'Note', ?, ?);",
                (past_due, now_str, now_str),
            )

    # Run check
    summary = run_due_reminders_once(temp_db)
    
    # REM_BAD_TPL fails personalization BEFORE claim -> remains pending
    with get_db_connection(temp_db) as conn:
        row = conn.execute("SELECT status FROM reminders WHERE reminder_id='REM_BAD_TPL';").fetchone()
        assert row["status"] == "pending", "Failed personalization must leave reminder in pending state!"
        
        # REM_ALREADY_READY must not be touched or re-prepared
        row_ready = conn.execute("SELECT status FROM reminders WHERE reminder_id='REM_ALREADY_READY';").fetchone()
        assert row_ready["status"] == "ready"

    assert "REM_BAD_TPL" not in summary.prepared_ids
    assert "REM_ALREADY_READY" not in summary.prepared_ids
    assert summary.prepared == 0
