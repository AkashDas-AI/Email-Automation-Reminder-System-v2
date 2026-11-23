"""Automated Tests for Logging & Report Generation (Phase 9)

Project: Email Automation & Reminder System
Author: Akash Das
Covers: Structured logging, handler deduplication, log file writing, activity history persistence,
data redaction, formula injection protection, report generation (email activity, reminder status counts,
reminder details, activity history), empty dataset handling, inclusive UTC date filtering,
attempted calculation invariants, and lossless schema migration.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import pytest

from email_automation.config import AppConfig
from email_automation.database import (
    get_activity_logs,
    get_db_connection,
    init_db,
    log_activity,
    migrate_db,
    update_dispatch_outcome,
)
from email_automation.logger import DEFAULT_LOG_FILE, get_logger, resolve_log_level, setup_logging
from email_automation.models import ActivityLog, PersonalizedEmail, ReportResult
from email_automation.report_generator import (
    FORMULA_PREFIXES,
    generate_activity_history_report,
    generate_email_activity_report,
    generate_reminder_details_report,
    generate_reminder_status_report,
    sanitize_csv_value,
)


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Provides an isolated temporary database with current Phase 9 schema."""
    db_file = tmp_path / "test_logging.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def sample_email_record(temp_db: Path) -> str:
    """Helper fixture to insert a valid contact, reminder, and prepared_email in the database."""
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'aarav@example.com', 'IT', 'Apex', ?);",
                (now_str,),
            )
            conn.execute(
                "INSERT INTO reminders VALUES ('REM001', 'CON001', 'Meeting', 'meeting', ?, 'simulated', 'M-1', 'Note 1', NULL, ?, ?);",
                (now_str, now_str, now_str),
            )
            conn.execute(
                """
                INSERT INTO prepared_emails VALUES (
                    'REM001', 'CON001', 'aarav@example.com', 'Aarav Sharma',
                    'meeting', 'Meeting Reminder: Sync session', '<p>Hello</p>', 'Hello', ?, 'M-1', ?
                );
                """,
                (now_str, now_str),
            )
    return "REM001"


# 1. Logger initialization
def test_logger_initialization(tmp_path: Path):
    log_file = tmp_path / "app.log"
    logger = setup_logging(log_level="DEBUG", log_file=log_file, console=False, logger_name="test_init")
    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.FileHandler)


# 2. Duplicate logger handler prevention
def test_duplicate_logger_handler_prevention(tmp_path: Path):
    log_file = tmp_path / "dedup.log"
    # Call setup_logging 5 times consecutively on the same namespace
    for _ in range(5):
        logger = setup_logging(log_level="INFO", log_file=log_file, console=True, logger_name="test_dedup")
    
    # Handlers must not multiply (1 console StreamHandler + 1 FileHandler = exactly 2)
    assert len(logger.handlers) == 2
    types = [type(h) for h in logger.handlers]
    assert logging.StreamHandler in types
    assert logging.FileHandler in types


# 3. Log file creation
def test_log_file_creation(tmp_path: Path):
    log_file = tmp_path / "nested" / "logs" / "test_run.log"
    logger = setup_logging(log_level="INFO", log_file=log_file, console=False, logger_name="test_file")
    logger.info("Application starting up under test verification.")
    
    assert log_file.is_file()
    content = log_file.read_text(encoding="utf-8")
    assert "Application starting up under test verification." in content
    assert "INFO" in content


# 4. Console logging
def test_console_logging(monkeypatch):
    out_buf = io.StringIO()
    logger = setup_logging(log_level="INFO", log_file=None, console=True, logger_name="test_console")
    logger.handlers[0].stream = out_buf
    logger.warning("Operator safety alert message.")
    
    output = out_buf.getvalue()
    assert "WARNING" in output
    assert "Operator safety alert message." in output


# 5. Activity history database initialization
def test_activity_history_database_initialization(temp_db: Path):
    with get_db_connection(temp_db) as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row["name"] for row in cursor.fetchall()}
        assert "activity_logs" in tables
        assert "schema_version" in tables

        idx_cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='activity_logs';")
        indexes = {row["name"] for row in idx_cursor.fetchall()}
        assert "idx_activity_logs_ts" in indexes
        assert "idx_activity_logs_event" in indexes
        assert "idx_activity_logs_severity" in indexes
        assert "idx_activity_logs_reminder" in indexes
        assert "idx_activity_logs_status" in indexes


# 6. Activity logs schema columns inspection
def test_activity_logs_schema_columns(temp_db: Path):
    """Verifies that activity_logs table provides all 9 required queryable fields."""
    with get_db_connection(temp_db) as conn:
        cursor = conn.execute("PRAGMA table_info(activity_logs);")
        cols = {row["name"]: row["type"] for row in cursor.fetchall()}
        
        required = [
            "log_id",
            "timestamp",
            "event_type",
            "severity",
            "reminder_id",
            "contact_id",
            "status",
            "message",
            "details",
        ]
        for col in required:
            assert col in cols, f"Missing required column '{col}' in activity_logs schema"


# 7. Persistent activity events
def test_persistent_activity_events(temp_db: Path):
    log_id = log_activity(
        db_path=temp_db,
        event_type="reminder_prepared",
        severity="INFO",
        status="ready",
        message="Reminder REM001 prepared successfully.",
        reminder_id="REM001",
        contact_id="CON001",
        details={"subject": "Test Subject"},
    )
    assert log_id is not None

    logs = get_activity_logs(temp_db, event_type="reminder_prepared")
    assert len(logs) == 1
    log = logs[0]
    assert log.event_type == "reminder_prepared"
    assert log.severity == "INFO"
    assert log.status == "ready"
    assert log.reminder_id == "REM001"
    assert log.contact_id == "CON001"
    assert "Reminder REM001 prepared successfully." in log.message
    assert "Test Subject" in str(log.details)


# 8. Activity event filtering (type, severity, status, dates)
def test_activity_event_filtering(temp_db: Path):
    now = datetime.now(timezone.utc)
    ts1 = (now - timedelta(days=2)).isoformat()
    ts2 = (now - timedelta(days=1)).isoformat()
    ts3 = now.isoformat()

    log_activity(temp_db, event_type="data_synced", severity="INFO", status="success", message="M1", timestamp=ts1)
    log_activity(temp_db, event_type="email_failed", severity="ERROR", status="failed", message="M2", timestamp=ts2)
    log_activity(temp_db, event_type="email_simulated", severity="INFO", status="simulated", message="M3", timestamp=ts3)

    # Filter by event_type
    imp_logs = get_activity_logs(temp_db, event_type="data_synced")
    assert len(imp_logs) == 1
    assert imp_logs[0].message == "M1"

    # Filter by severity
    err_logs = get_activity_logs(temp_db, severity="ERROR")
    assert len(err_logs) == 1
    assert err_logs[0].message == "M2"

    # Filter by status
    sim_logs = get_activity_logs(temp_db, status="simulated")
    assert len(sim_logs) == 1
    assert sim_logs[0].message == "M3"

    # Filter by date range
    range_logs = get_activity_logs(temp_db, start_date=ts2, end_date=ts3)
    msgs = {l.message for l in range_logs}
    assert "M2" in msgs
    assert "M3" in msgs
    assert "M1" not in msgs


# 9. Fail-soft activity logging
def test_fail_soft_activity_logging(tmp_path: Path):
    """Verifies that an unhandled database error during activity logging returns None without raising."""
    invalid_path = tmp_path / "non_existent_dir" / "bad.db"
    res = log_activity(invalid_path, event_type="test", message="Should fail soft")
    assert res is None


# 10. Sensitive data redaction
def test_sensitive_data_redaction(temp_db: Path, tmp_path: Path):
    log_file = tmp_path / "sensitive.log"
    logger = setup_logging(log_level="DEBUG", log_file=log_file, console=False, logger_name="test_secrets")
    
    secret_pass = "super_secret_gmail_app_pw_1234"
    config = AppConfig(dry_run=True, smtp_password=secret_pass)
    
    config_str = repr(config)
    assert secret_pass not in config_str
    assert "********" in config_str

    logger.info("Current configuration: %s", config)
    file_content = log_file.read_text(encoding="utf-8")
    assert secret_pass not in file_content

    log_activity(
        db_path=temp_db,
        event_type="email_simulated",
        severity="INFO",
        status="simulated",
        message="Simulated dispatch for REM001",
        details={"recipient_email": "user@example.com"},
    )
    with get_db_connection(temp_db) as conn:
        row = conn.execute("SELECT message, details FROM activity_logs WHERE event_type='email_simulated';").fetchone()
        assert secret_pass not in row["message"]
        assert secret_pass not in (row["details"] or "")


# 11. Email activity CSV export with explicit timestamps and headers
def test_email_activity_csv_export(temp_db: Path, sample_email_record: str, tmp_path: Path):
    rep_dir = tmp_path / "reports"
    res = generate_email_activity_report(db_path=temp_db, output_dir=rep_dir)
    assert isinstance(res, ReportResult)
    assert res.report_type == "email_activity"
    assert res.file_path.is_file()
    assert res.record_count == 1

    with open(res.file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1
        r = rows[0]
        assert r["reminder_id"] == "REM001"
        assert r["contact_id"] == "CON001"
        assert r["recipient_email"] == "aarav@example.com"
        assert r["dispatch_status"] == "simulated"
        assert "Meeting Reminder" in r["subject"]
        assert r["prepared_timestamp"] != ""
        assert r["dispatch_timestamp"] != ""
        assert r["safe_failure_reason"] == ""


# 12. Reminder status count report provides counts for all 7 statuses
def test_reminder_status_csv_export(temp_db: Path, sample_email_record: str, tmp_path: Path):
    rep_dir = tmp_path / "reports"
    res = generate_reminder_status_report(db_path=temp_db, output_dir=rep_dir)
    assert res.report_type == "reminder_status"
    assert res.file_path.is_file()

    with open(res.file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        data = {row["status"]: row["count"] for row in reader}
        assert data["total"] == "1"
        assert data["simulated"] == "1"
        assert data["pending"] == "0"
        assert data["ready"] == "0"
        assert data["processing"] == "0"
        assert data["sent"] == "0"
        assert data["failed"] == "0"
        assert data["delivery_unknown"] == "0"
        assert data["attempted"] == "1"
        assert data["success_rate"] == "100.0%"


# 13. Detailed reminder snapshot report export
def test_reminder_details_report_export(temp_db: Path, sample_email_record: str, tmp_path: Path):
    rep_dir = tmp_path / "reports_details"
    res = generate_reminder_details_report(db_path=temp_db, output_dir=rep_dir)
    assert res.report_type == "reminder_details"
    assert res.file_path.is_file()
    assert res.record_count == 1

    with open(res.file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["reminder_id"] == "REM001"
        assert rows[0]["contact_name"] == "Aarav Sharma"
        assert rows[0]["status"] == "simulated"


# 14. Activity history CSV export
def test_activity_history_csv_export(temp_db: Path, tmp_path: Path):
    log_activity(temp_db, event_type="data_synced", severity="INFO", status="success", message="Import done")
    log_activity(temp_db, event_type="email_simulated", severity="INFO", status="simulated", message="Simulation done")

    rep_dir = tmp_path / "reports"
    res = generate_activity_history_report(db_path=temp_db, output_dir=rep_dir)
    assert res.report_type == "activity_history"
    assert res.file_path.is_file()
    assert res.record_count >= 2

    with open(res.file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        events = [row["event_type"] for row in reader]
        assert "data_synced" in events
        assert "email_simulated" in events


# 15. Empty report generation handles zero records gracefully
def test_empty_report_generation(tmp_path: Path):
    empty_db = tmp_path / "empty.db"
    init_db(empty_db)
    rep_dir = tmp_path / "reports_empty"

    # Email activity on empty database
    res1 = generate_email_activity_report(empty_db, output_dir=rep_dir)
    assert res1.record_count == 0
    with open(res1.file_path, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert "reminder_id" in header
        assert len(list(reader)) == 0

    # Reminder status on empty database
    res2 = generate_reminder_status_report(empty_db, output_dir=rep_dir)
    with open(res2.file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        metrics = {r["status"]: r["count"] for r in reader}
        assert metrics["total"] == "0"
        assert metrics["pending"] == "0"
        assert metrics["ready"] == "0"
        assert metrics["processing"] == "0"
        assert metrics["simulated"] == "0"
        assert metrics["sent"] == "0"
        assert metrics["failed"] == "0"
        assert metrics["delivery_unknown"] == "0"
        assert metrics["attempted"] == "0"
        assert metrics["success_rate"] == "0.0%"

    # Detailed snapshot on empty database
    res3 = generate_reminder_details_report(empty_db, output_dir=rep_dir)
    assert res3.record_count == 0

    # Activity history on empty database
    res4 = generate_activity_history_report(empty_db, output_dir=rep_dir)
    assert res4.file_path.is_file()


# 16. Inclusive UTC date filtering on boundaries
def test_utc_date_filtering_inclusive_boundaries(temp_db: Path, tmp_path: Path):
    """Verifies that date filtering in UTC is strictly inclusive on both start and end boundaries."""
    t_before = "2026-11-14T23:59:59Z"
    t_start = "2026-11-15T00:00:00Z"
    t_mid = "2026-11-15T12:00:00Z"
    t_end = "2026-11-15T23:59:59Z"
    t_after = "2026-11-16T00:00:01Z"

    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute("INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);", (t_mid,))
            conn.execute("INSERT INTO reminders VALUES ('R_BEFORE', 'CON001', 'T', 'k', ?, 'simulated', 'R', 'N', NULL, ?, ?);", (t_before, t_before, t_before))
            conn.execute("INSERT INTO reminders VALUES ('R_START', 'CON001', 'T', 'k', ?, 'simulated', 'R', 'N', NULL, ?, ?);", (t_start, t_start, t_start))
            conn.execute("INSERT INTO reminders VALUES ('R_MID', 'CON001', 'T', 'k', ?, 'simulated', 'R', 'N', NULL, ?, ?);", (t_mid, t_mid, t_mid))
            conn.execute("INSERT INTO reminders VALUES ('R_END', 'CON001', 'T', 'k', ?, 'simulated', 'R', 'N', NULL, ?, ?);", (t_end, t_end, t_end))
            conn.execute("INSERT INTO reminders VALUES ('R_AFTER', 'CON001', 'T', 'k', ?, 'simulated', 'R', 'N', NULL, ?, ?);", (t_after, t_after, t_after))

    # Test filtering using date strings (YYYY-MM-DD inclusive)
    res = generate_email_activity_report(temp_db, output_dir=tmp_path, start_date="2026-11-15", end_date="2026-11-15")
    assert res.record_count == 3
    with open(res.file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        ids = {r["reminder_id"] for r in reader}
        assert ids == {"R_START", "R_MID", "R_END"}
        assert "R_BEFORE" not in ids
        assert "R_AFTER" not in ids


# 17. CSV headers and UTF-8 encoding
def test_csv_headers_and_encoding(temp_db: Path, sample_email_record: str, tmp_path: Path):
    res = generate_email_activity_report(temp_db, output_dir=tmp_path)
    raw_bytes = res.file_path.read_bytes()
    decoded = raw_bytes.decode("utf-8")
    assert "reminder_id" in decoded

    expected_headers = [
        "reminder_id",
        "contact_id",
        "recipient_email",
        "template_key",
        "subject",
        "due_at",
        "dispatch_status",
        "prepared_timestamp",
        "dispatch_timestamp",
        "safe_failure_reason",
    ]
    with open(res.file_path, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        actual_headers = next(reader)
        assert actual_headers == expected_headers


# 18. CSV formula injection protection
def test_formula_injection_protection(temp_db: Path, tmp_path: Path):
    """Verifies that dangerous formula characters (=, +, -, @) are prefixed with ' in CSV without altering DB values."""
    now_str = datetime.now(timezone.utc).isoformat()
    raw_email = "=admin@company.com"
    raw_subject = "+12345678"
    raw_notes = "-cmd|' /C calc'!A0"
    raw_company = "@Apex Corp"

    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES ('CON_INJ', '=Hacker', '+Evil', ?, 'IT', ?, ?);",
                (raw_email, raw_company, now_str),
            )
            conn.execute(
                "INSERT INTO reminders VALUES ('REM_INJ', 'CON_INJ', 'Test', 'general', ?, 'simulated', 'REF1', ?, '=ERROR_CODE', ?, ?);",
                (now_str, raw_notes, now_str, now_str),
            )
            conn.execute(
                """
                INSERT INTO prepared_emails VALUES (
                    'REM_INJ', 'CON_INJ', ?, '=Hacker', 'general', ?, '<p>Body</p>', 'Body', ?, 'REF1', ?
                );
                """,
                (raw_email, raw_subject, now_str, now_str),
            )

    log_activity(
        db_path=temp_db,
        event_type="=EXEC_SHELL",
        severity="INFO",
        status="success",
        message="+Message text",
        details={"notes": raw_notes},
    )

    # 1. Verify Email Activity Report CSV escaping
    res_email = generate_email_activity_report(temp_db, output_dir=tmp_path)
    with open(res_email.file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r["reminder_id"] == "REM_INJ"]
        assert len(rows) == 1
        r = rows[0]
        # In CSV, values MUST be prefixed with single quote
        assert r["recipient_email"] == f"'{raw_email}"
        assert r["subject"] == f"'{raw_subject}"
        assert r["safe_failure_reason"] == "'=ERROR_CODE"

    # 2. Verify Reminder Details Report CSV escaping
    res_details = generate_reminder_details_report(temp_db, output_dir=tmp_path)
    with open(res_details.file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r["reminder_id"] == "REM_INJ"]
        assert len(rows) == 1
        assert rows[0]["company"] == f"'{raw_company}"
        assert rows[0]["notes"] == f"'{raw_notes}"

    # 3. Verify Activity History Report CSV escaping
    res_act = generate_activity_history_report(temp_db, output_dir=tmp_path)
    with open(res_act.file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r["event_type"] == "'=EXEC_SHELL"]
        assert len(rows) == 1
        assert rows[0]["message"] == "'+Message text"

    # 4. Verify SQLite database values were NOT modified
    with get_db_connection(temp_db) as conn:
        c_row = conn.execute("SELECT email, company FROM contacts WHERE contact_id='CON_INJ';").fetchone()
        assert c_row["email"] == raw_email  # still "=admin@company.com" without leading quote
        assert c_row["company"] == raw_company

        r_row = conn.execute("SELECT notes, dispatch_error FROM reminders WHERE reminder_id='REM_INJ';").fetchone()
        assert r_row["notes"] == raw_notes
        assert r_row["dispatch_error"] == "=ERROR_CODE"


# 19. Reminder status counts covering all seven reminder statuses & exact attempted formula
def test_reminder_status_counts_all_seven_statuses(temp_db: Path, tmp_path: Path):
    """Verifies that:
    - Counts for all seven statuses are accurately computed from actual records.
    - Attempted = Simulated + SMTP Accepted (sent) + Failed.
    - Pending, ready, and processing are strictly excluded from the attempted denominator.
    - delivery_unknown is excluded from the success-rate denominator (tracked separately).
    - Success rate = (Simulated + Sent) / Attempted.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    status_fixture = [
        ("pending", 3),
        ("ready", 2),
        ("processing", 1),
        ("simulated", 4),
        ("sent", 6),
        ("failed", 2),
        ("delivery_unknown", 1),
    ]

    total_expected = sum(count for _, count in status_fixture)  # 3+2+1+4+6+2+1 = 19

    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute("INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);", (now_str,))
            rem_idx = 0
            for status, count in status_fixture:
                for _ in range(count):
                    rem_idx += 1
                    conn.execute(
                        f"INSERT INTO reminders VALUES ('REM_{rem_idx}', 'CON001', 'T', 'k', ?, ?, 'REF', 'N', NULL, ?, ?);",
                        (now_str, status, now_str, now_str),
                    )

    res = generate_reminder_status_report(temp_db, output_dir=tmp_path)
    with open(res.file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        data = {r["status"]: r["count"] for r in reader}

        # Verify all 7 individual statuses match exact fixture counts
        assert data["pending"] == "3"
        assert data["ready"] == "2"
        assert data["processing"] == "1"
        assert data["simulated"] == "4"
        assert data["sent"] == "6"
        assert data["failed"] == "2"
        assert data["delivery_unknown"] == "1"
        assert data["total"] == str(total_expected)

        # Invariant: Attempted = Simulated (4) + Sent (6) + Failed (2) = 12
        # Excludes: pending (3), ready (2), processing (1), delivery_unknown (1)
        expected_attempted = 4 + 6 + 2  # 12
        assert data["attempted"] == "12"

        # Success rate = (4 + 6) / 12 = 10 / 12 = 83.3%
        expected_rate = (10 / 12) * 100.0
        assert data["success_rate"] == f"{expected_rate:.1f}%"


# 20. Simulated and SMTP-accepted counts remain separate
def test_simulated_and_smtp_accepted_counts_separate(temp_db: Path, tmp_path: Path):
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute("INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);", (now_str,))
            conn.execute("INSERT INTO reminders VALUES ('REM_SIM', 'CON001', 'T', 'k', ?, 'simulated', 'R', 'N', NULL, ?, ?);", (now_str, now_str, now_str))
            conn.execute("INSERT INTO reminders VALUES ('REM_SENT', 'CON001', 'T', 'k', ?, 'sent', 'R', 'N', NULL, ?, ?);", (now_str, now_str, now_str))

    res = generate_reminder_status_report(temp_db, output_dir=tmp_path)
    with open(res.file_path, mode="r", encoding="utf-8") as f:
        data = {r["status"]: r["count"] for r in csv.DictReader(f)}
        assert data["simulated"] == "1"
        assert data["sent"] == "1"
        assert data["attempted"] == "2"
        assert data["success_rate"] == "100.0%"


# 21. Report generation does not modify reminder statuses
def test_report_generation_does_not_modify_reminder_statuses(temp_db: Path, sample_email_record: str, tmp_path: Path):
    with get_db_connection(temp_db) as conn:
        status_before = conn.execute("SELECT status FROM reminders WHERE reminder_id='REM001';").fetchone()[0]

    generate_email_activity_report(temp_db, output_dir=tmp_path)
    generate_reminder_status_report(temp_db, output_dir=tmp_path)
    generate_reminder_details_report(temp_db, output_dir=tmp_path)
    generate_activity_history_report(temp_db, output_dir=tmp_path)

    with get_db_connection(temp_db) as conn:
        status_after = conn.execute("SELECT status FROM reminders WHERE reminder_id='REM001';").fetchone()[0]

    assert status_after == status_before == "simulated"


# 22. Comprehensive Phase 8 to Phase 9 schema migration and foreign key check
def test_phase8_to_phase9_migration_comprehensive(tmp_path: Path):
    """Creates a database strictly on the Phase 8 schema and verifies lossless upgrade to Phase 9."""
    db_file = tmp_path / "phase8_legacy.db"
    now_str = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    with conn:
        conn.executescript(
            """
            CREATE TABLE contacts (
                contact_id TEXT PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                department TEXT NOT NULL,
                company TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE reminders (
                reminder_id TEXT PRIMARY KEY,
                contact_id TEXT NOT NULL,
                reminder_type TEXT NOT NULL,
                template_key TEXT NOT NULL,
                due_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'ready', 'processing', 'simulated', 'sent', 'failed', 'delivery_unknown')),
                reference_id TEXT NOT NULL,
                notes TEXT NOT NULL,
                dispatch_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (contact_id) REFERENCES contacts (contact_id) ON DELETE CASCADE
            );

            CREATE TABLE prepared_emails (
                reminder_id TEXT PRIMARY KEY,
                contact_id TEXT NOT NULL,
                recipient_email TEXT NOT NULL,
                recipient_name TEXT NOT NULL,
                template_key TEXT NOT NULL,
                subject TEXT NOT NULL,
                html_body TEXT NOT NULL,
                text_body TEXT NOT NULL,
                due_at TEXT NOT NULL,
                reference_id TEXT NOT NULL,
                prepared_at TEXT NOT NULL,
                FOREIGN KEY (reminder_id) REFERENCES reminders (reminder_id) ON DELETE CASCADE
            );

            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            INSERT INTO schema_version VALUES (8, datetime('now'));
            """
        )

        conn.execute("INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'aarav@example.com', 'IT', 'Apex', ?);", (now_str,))
        conn.execute("INSERT INTO reminders VALUES ('REM001', 'CON001', 'Meeting', 'meeting', ?, 'simulated', 'M-1', 'Notes', 'No error', ?, ?);", (now_str, now_str, now_str))
        conn.execute(
            """
            INSERT INTO prepared_emails VALUES (
                'REM001', 'CON001', 'aarav@example.com', 'Aarav Sharma',
                'meeting', 'Subject 1', '<p>Body</p>', 'Body', ?, 'M-1', ?
            );
            """,
            (now_str, now_str),
        )
    conn.close()

    # Verify activity_logs table does not exist prior to migration
    with get_db_connection(db_file) as conn:
        tbls = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
        assert "activity_logs" not in tbls

    # Run migration
    applied = migrate_db(db_file)
    assert applied is True

    # Verify Phase 9 tables, indexes, and preservation of existing records
    with get_db_connection(db_file) as conn:
        tbls_after = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()}
        assert "activity_logs" in tbls_after

        # Verify activity_logs schema columns
        act_cols = {r["name"] for r in conn.execute("PRAGMA table_info(activity_logs);").fetchall()}
        assert {"log_id", "timestamp", "event_type", "severity", "reminder_id", "contact_id", "status", "message", "details"}.issubset(act_cols)

        # Verify contacts, reminders, prepared_emails data preserved
        contact = conn.execute("SELECT * FROM contacts WHERE contact_id='CON001';").fetchone()
        assert contact["first_name"] == "Aarav"

        reminder = conn.execute("SELECT * FROM reminders WHERE reminder_id='REM001';").fetchone()
        assert reminder["status"] == "simulated"
        assert reminder["dispatch_error"] == "No error"

        prep = conn.execute("SELECT * FROM prepared_emails WHERE reminder_id='REM001';").fetchone()
        assert prep["subject"] == "Subject 1"

        ver = conn.execute("SELECT max(version) FROM schema_version;").fetchone()[0]
        assert ver == 9

        # PRAGMA foreign_key_check must return ZERO violations
        fk_check = conn.execute("PRAGMA foreign_key_check;").fetchall()
        assert len(fk_check) == 0

    # Second migration call must be strictly idempotent
    assert migrate_db(db_file) is False


# 23. Complete activity-event instrumentation across core workflows
def test_complete_activity_event_instrumentation(temp_db: Path):
    """Verifies that meaningful activity records are recorded across application lifecycle stages."""
    # 1. Database initialization event was recorded by temp_db fixture
    init_logs = get_activity_logs(temp_db, event_type="database_initialized")
    assert len(init_logs) >= 1

    # 2. Database migration event
    migrate_db(temp_db)

    # 3. Reminder preparation event
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute("INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);", (now_str,))
            conn.execute("INSERT INTO reminders VALUES ('REM001', 'CON001', 'Meeting', 'meeting', ?, 'pending', 'M-1', 'Notes', NULL, ?, ?);", (now_str, now_str, now_str))

    p_email = PersonalizedEmail(
        reminder_id="REM001",
        contact_id="CON001",
        recipient_email="a@example.com",
        recipient_name="Aarav Sharma",
        template_key="meeting",
        subject="Meeting Sync",
        html_body="<p>Body</p>",
        text_body="Body",
        due_at=now_str,
        reference_id="M-1",
    )
    from email_automation.database import transition_reminder_to_ready
    transition_reminder_to_ready(temp_db, "REM001", p_email)

    prep_logs = get_activity_logs(temp_db, event_type="reminder_prepared")
    assert len(prep_logs) == 1
    assert prep_logs[0].reminder_id == "REM001"
    assert prep_logs[0].status == "ready"


# 24. Restrict Email Activity Report to actual dispatch attempts
def test_email_activity_report_restricts_to_dispatch_attempts(temp_db: Path, tmp_path: Path):
    """Verifies that the Email Activity Report:
    - Includes actual dispatch outcomes: simulated, sent, failed, delivery_unknown.
    - Strictly excludes non-attempted statuses: pending, ready, processing.
    - Correctly populates dispatch_status and dispatch_timestamp.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    fixture = [
        ("REM_PEND_1", "pending", None),
        ("REM_PEND_2", "pending", None),
        ("REM_READY_1", "ready", None),
        ("REM_READY_2", "ready", None),
        ("REM_PROC_1", "processing", None),
        ("REM_SIM_1", "simulated", None),
        ("REM_SIM_2", "simulated", None),
        ("REM_SENT_1", "sent", None),
        ("REM_SENT_2", "sent", None),
        ("REM_FAIL_1", "failed", "Invalid recipient mailbox"),
        ("REM_UNK_1", "delivery_unknown", "Socket disconnected post-DATA"),
    ]

    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute("INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'aarav@example.com', 'IT', 'Apex', ?);", (now_str,))
            for r_id, status, err in fixture:
                conn.execute(
                    "INSERT INTO reminders VALUES (?, 'CON001', 'Meeting', 'meeting', ?, ?, 'M-1', 'Notes', ?, ?, ?);",
                    (r_id, now_str, status, err, now_str, now_str),
                )
                # Prepared email record for staged reminders
                if status != "pending":
                    conn.execute(
                        """
                        INSERT INTO prepared_emails VALUES (
                            ?, 'CON001', 'aarav@example.com', 'Aarav Sharma',
                            'meeting', 'Meeting Sync', '<p>Body</p>', 'Body', ?, 'M-1', ?
                        );
                        """,
                        (r_id, now_str, now_str),
                    )

    # 1. Generate Email Activity Report
    res = generate_email_activity_report(temp_db, output_dir=tmp_path)
    # Total attempted = 2 (simulated) + 2 (sent) + 1 (failed) + 1 (delivery_unknown) = 6
    assert res.record_count == 6

    with open(res.file_path, mode="r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        assert len(rows) == 6

        reported_ids = {r["reminder_id"] for r in rows}
        reported_statuses = {r["dispatch_status"] for r in rows}

        # Verify excluded statuses
        assert "REM_PEND_1" not in reported_ids
        assert "REM_PEND_2" not in reported_ids
        assert "REM_READY_1" not in reported_ids
        assert "REM_READY_2" not in reported_ids
        assert "REM_PROC_1" not in reported_ids
        assert "pending" not in reported_statuses
        assert "ready" not in reported_statuses
        assert "processing" not in reported_statuses

        # Verify included outcomes
        assert reported_ids == {"REM_SIM_1", "REM_SIM_2", "REM_SENT_1", "REM_SENT_2", "REM_FAIL_1", "REM_UNK_1"}
        assert reported_statuses == {"simulated", "sent", "failed", "delivery_unknown"}

        # Verify specific outcome attributes
        failed_row = next(r for r in rows if r["reminder_id"] == "REM_FAIL_1")
        assert failed_row["safe_failure_reason"] == "Invalid recipient mailbox"
        assert failed_row["dispatch_timestamp"] != ""

        unk_row = next(r for r in rows if r["reminder_id"] == "REM_UNK_1")
        assert unk_row["safe_failure_reason"] == "Socket disconnected post-DATA"
        assert unk_row["dispatch_status"] == "delivery_unknown"

    # 2. Reminder Status Report must continue to show all seven statuses
    res_status = generate_reminder_status_report(temp_db, output_dir=tmp_path)
    with open(res_status.file_path, mode="r", encoding="utf-8") as f:
        status_map = {r["status"]: r["count"] for r in csv.DictReader(f)}
        assert status_map["pending"] == "2"
        assert status_map["ready"] == "2"
        assert status_map["processing"] == "1"
        assert status_map["simulated"] == "2"
        assert status_map["sent"] == "2"
        assert status_map["failed"] == "1"
        assert status_map["delivery_unknown"] == "1"
        assert status_map["total"] == "11"
        # Attempted = 2 (simulated) + 2 (sent) + 1 (failed) = 5 (excludes delivery_unknown)
        assert status_map["attempted"] == "5"

    # 3. Reminder Details Report may continue to show all 11 reminder records
    res_details = generate_reminder_details_report(temp_db, output_dir=tmp_path)
    assert res_details.record_count == 11


# 25. Migration from earlier Phase 9 activity_logs schema
def test_migration_from_earlier_phase9_activity_logs_schema(tmp_path: Path):
    """Verifies that an activity_logs table created under the earlier Phase 9 schema
    (using 'id', 'details_json', and lacking 'status'/'message') is upgraded safely:
    - Existing activity records are preserved without data loss.
    - 'id' is mapped to 'log_id'.
    - 'details_json' is mapped to 'details'.
    - New fields 'status' and 'message' receive safe, honest migration values.
    - All 9 columns and 5 indexes exist.
    - PRAGMA foreign_key_check reports zero violations.
    - Second migration call is strictly idempotent.
    """
    db_file = tmp_path / "earlier_phase9.db"
    now_str = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    with conn:
        conn.executescript(
            """
            CREATE TABLE contacts (
                contact_id TEXT PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                department TEXT NOT NULL,
                company TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE reminders (
                reminder_id TEXT PRIMARY KEY,
                contact_id TEXT NOT NULL,
                reminder_type TEXT NOT NULL,
                template_key TEXT NOT NULL,
                due_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'ready', 'processing', 'simulated', 'sent', 'failed', 'delivery_unknown')),
                reference_id TEXT NOT NULL,
                notes TEXT NOT NULL,
                dispatch_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (contact_id) REFERENCES contacts (contact_id) ON DELETE CASCADE
            );

            CREATE TABLE prepared_emails (
                reminder_id TEXT PRIMARY KEY,
                contact_id TEXT NOT NULL,
                recipient_email TEXT NOT NULL,
                recipient_name TEXT NOT NULL,
                template_key TEXT NOT NULL,
                subject TEXT NOT NULL,
                html_body TEXT NOT NULL,
                text_body TEXT NOT NULL,
                due_at TEXT NOT NULL,
                reference_id TEXT NOT NULL,
                prepared_at TEXT NOT NULL,
                FOREIGN KEY (reminder_id) REFERENCES reminders (reminder_id) ON DELETE CASCADE
            );

            -- Earlier Phase 9 activity_logs schema (id, details_json, no status, no message)
            CREATE TABLE activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                reminder_id TEXT,
                contact_id TEXT,
                details_json TEXT
            );
            CREATE INDEX idx_activity_logs_ts ON activity_logs (timestamp);
            CREATE INDEX idx_activity_logs_event ON activity_logs (event_type);
            CREATE INDEX idx_activity_logs_severity ON activity_logs (severity);
            CREATE INDEX idx_activity_logs_reminder ON activity_logs (reminder_id);

            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            INSERT INTO schema_version VALUES (9, datetime('now'));
            """
        )

        # Insert historical contacts and reminders
        conn.execute("INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'aarav@example.com', 'IT', 'Apex', ?);", (now_str,))
        conn.execute("INSERT INTO reminders VALUES ('REM001', 'CON001', 'Meeting', 'meeting', ?, 'simulated', 'M-1', 'Notes', NULL, ?, ?);", (now_str, now_str, now_str))

        # Insert historical activity_logs records using the old schema
        conn.execute(
            """
            INSERT INTO activity_logs (timestamp, event_type, severity, reminder_id, contact_id, details_json)
            VALUES (?, 'reminder_prepared', 'INFO', 'REM001', 'CON001', '{"subject": "Sync session"}');
            """,
            (now_str,),
        )
        conn.execute(
            """
            INSERT INTO activity_logs (timestamp, event_type, severity, reminder_id, contact_id, details_json)
            VALUES (?, 'email_simulated', 'INFO', 'REM001', 'CON001', '{"recipient": "aarav@example.com"}');
            """,
            (now_str,),
        )
        conn.execute(
            """
            INSERT INTO activity_logs (timestamp, event_type, severity, reminder_id, contact_id, details_json)
            VALUES (?, 'email_failed', 'ERROR', 'REM001', 'CON001', '{"error": "SMTP auth failed"}');
            """,
            (now_str,),
        )
        conn.execute(
            """
            INSERT INTO activity_logs (timestamp, event_type, severity, reminder_id, contact_id, details_json)
            VALUES (?, 'data_synced', 'INFO', NULL, NULL, '{"contacts": 20, "reminders": 24}');
            """,
            (now_str,),
        )
    conn.close()

    # Verify old schema columns before migration
    with get_db_connection(db_file) as conn:
        cols_before = {r["name"] for r in conn.execute("PRAGMA table_info(activity_logs);").fetchall()}
        assert "id" in cols_before
        assert "details_json" in cols_before
        assert "log_id" not in cols_before
        assert "status" not in cols_before
        assert "message" not in cols_before

    # Run migration
    applied = migrate_db(db_file)
    assert applied is True

    # Verify upgraded schema, data preservation, and index presence
    with get_db_connection(db_file) as conn:
        cols_after = {r["name"] for r in conn.execute("PRAGMA table_info(activity_logs);").fetchall()}
        required = {"log_id", "timestamp", "event_type", "severity", "reminder_id", "contact_id", "status", "message", "details"}
        assert required == cols_after
        assert "id" not in cols_after
        assert "details_json" not in cols_after

        # Verify all 5 indexes exist
        idx_names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='activity_logs';").fetchall()}
        assert "idx_activity_logs_ts" in idx_names
        assert "idx_activity_logs_event" in idx_names
        assert "idx_activity_logs_severity" in idx_names
        assert "idx_activity_logs_reminder" in idx_names
        assert "idx_activity_logs_status" in idx_names

        # Verify record count and data mapping: 4 historical records + 1 migration completion log
        rows = conn.execute("SELECT * FROM activity_logs ORDER BY log_id ASC;").fetchall()
        assert len(rows) == 5
        assert rows[4]["event_type"] == "database_migrated"

        # Record 1: reminder_prepared -> status='ready'
        assert rows[0]["log_id"] == 1
        assert rows[0]["event_type"] == "reminder_prepared"
        assert rows[0]["status"] == "ready"
        assert "Sync session" in rows[0]["details"]
        assert rows[0]["message"] != ""

        # Record 2: email_simulated -> status='simulated'
        assert rows[1]["log_id"] == 2
        assert rows[1]["event_type"] == "email_simulated"
        assert rows[1]["status"] == "simulated"
        assert "aarav@example.com" in rows[1]["details"]

        # Record 3: email_failed -> status='failed'
        assert rows[2]["log_id"] == 3
        assert rows[2]["event_type"] == "email_failed"
        assert rows[2]["status"] == "failed"
        assert "SMTP auth failed" in rows[2]["details"]

        # Record 4: data_synced -> status='recorded'
        assert rows[3]["log_id"] == 4
        assert rows[3]["event_type"] == "data_synced"
        assert rows[3]["status"] == "recorded"
        assert "20" in rows[3]["details"]

        # Verify PRAGMA foreign_key_check reports zero violations
        fk_check = conn.execute("PRAGMA foreign_key_check;").fetchall()
        assert len(fk_check) == 0

    # Second migration call must be safe and idempotent
    assert migrate_db(db_file) is False

