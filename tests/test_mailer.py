"""Automated Tests for Email Sending & Dispatch Module (Phase 8)

Author: Akash Das
Covers: Dry-run transport, live SMTP safety gates, recipient allowlisting, MIME assembly,
STARTTLS protocol sequencing, error handling (auth, transmission, ambiguous timeout),
concurrency claim exclusivity, and zero secret exposure.
"""

from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
import smtplib
import socket
from unittest.mock import MagicMock, call, patch
import pytest

from email_automation.config import AppConfig, ConfigurationError
from email_automation.database import (
    claim_ready_emails_for_dispatch,
    get_all_prepared_emails,
    get_db_connection,
    get_stale_processing_reminders,
    init_db,
    migrate_db,
    reconcile_stale_processing_records,
    transition_reminder_to_ready,
    update_dispatch_outcome,
)
from email_automation.mailer import (
    DryRunTransport,
    GmailSMTPTransport,
    build_mime_message,
    dispatch_ready_emails,
)
from email_automation.models import DispatchResult, DispatchSummary, PersonalizedEmail


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Fixture providing an isolated temporary database with schema initialized."""
    db_file = tmp_path / "test_mailer.db"
    init_db(db_file)
    return db_file


@pytest.fixture
def sample_prepared_email() -> PersonalizedEmail:
    """Fixture providing a mock prepared email ready for dispatch."""
    return PersonalizedEmail(
        reminder_id="REM001",
        contact_id="CON001",
        recipient_email="authorized_user@example.com",
        recipient_name="Aarav Sharma",
        template_key="meeting",
        subject="Meeting Reminder: Architecture Sync [Ref: #MTG-101]",
        html_body="<p>Hello Aarav, your meeting is scheduled.</p>",
        text_body="Hello Aarav, your meeting is scheduled.",
        due_at="2027-01-15T10:00:00Z",
        reference_id="MTG-101",
    )


@pytest.fixture
def mock_config_dry_run() -> AppConfig:
    return AppConfig(dry_run=True)


@pytest.fixture
def mock_config_live() -> AppConfig:
    return AppConfig(
        dry_run=False,
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_username="test_sender@gmail.com",
        smtp_password="dummy_app_password",
        smtp_allowed_recipients=("authorized_user@example.com",),
        email_from="test_sender@gmail.com",
        email_from_name="Akash Das Dispatcher",
    )


def seed_ready_reminder(db_path: Path, email: PersonalizedEmail) -> None:
    """Helper to stage a contact, reminder, and prepared_email in 'ready' status."""
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(db_path) as conn:
        with conn:
            conn.execute(
                "INSERT INTO contacts VALUES (?, 'Aarav', 'Sharma', ?, 'IT', 'Apex', ?);",
                (email.contact_id, email.recipient_email, now_str),
            )
            conn.execute(
                "INSERT INTO reminders VALUES (?, ?, 'Meeting', ?, ?, 'ready', ?, 'Note', NULL, ?, ?);",
                (email.reminder_id, email.contact_id, email.template_key, email.due_at, email.reference_id, now_str, now_str),
            )
            conn.execute(
                """
                INSERT INTO prepared_emails (
                    reminder_id, contact_id, recipient_email, recipient_name,
                    template_key, subject, html_body, text_body, due_at, reference_id, prepared_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    email.reminder_id, email.contact_id, email.recipient_email, email.recipient_name,
                    email.template_key, email.subject, email.html_body, email.text_body, email.due_at, email.reference_id, now_str
                ),
            )


# 1. Dry-run mode simulates successfully
def test_dry_run_simulates_successfully(sample_prepared_email):
    res = DryRunTransport.send(sample_prepared_email)
    assert isinstance(res, DispatchResult)
    assert res.status == "simulated"
    assert res.reminder_id == sample_prepared_email.reminder_id
    assert res.recipient_email == sample_prepared_email.recipient_email
    assert res.error_message is None


# 2. Dry-run makes zero SMTP connections
def test_dry_run_makes_zero_smtp_connections(monkeypatch, temp_db: Path, sample_prepared_email):
    def forbidden_smtp(*args, **kwargs):
        raise AssertionError("SMTP constructor was called during dry-run!")

    monkeypatch.setattr(smtplib, "SMTP", forbidden_smtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", forbidden_smtp)

    seed_ready_reminder(temp_db, sample_prepared_email)
    summary = dispatch_ready_emails(db_path=temp_db, config=AppConfig(dry_run=True))
    assert summary.simulated == 1
    assert summary.smtp_accepted == 0
    assert summary.failed == 0

    with get_db_connection(temp_db) as conn:
        status = conn.execute("SELECT status FROM reminders WHERE reminder_id='REM001';").fetchone()[0]
        assert status == "simulated"


# 3. Live sending refuses missing credentials
def test_live_sending_refuses_missing_credentials(temp_db: Path):
    bad_live_config = AppConfig(dry_run=False, smtp_username=None, smtp_password=None, email_from=None)
    with pytest.raises(Exception):
        # Even if confirmed, mailer or config validation must reject incomplete credentials
        dispatch_ready_emails(temp_db, config=bad_live_config, confirm_live_send=True)


# 4. Live sending refuses absent CLI confirmation
def test_live_sending_refuses_absent_cli_confirmation(temp_db: Path, mock_config_live):
    with pytest.raises(ConfigurationError, match="--confirm-live-send"):
        dispatch_ready_emails(temp_db, config=mock_config_live, confirm_live_send=False)


# 5. Live sending refuses an empty recipient allowlist
def test_live_sending_refuses_empty_recipient_allowlist(sample_prepared_email):
    empty_allowlist_config = AppConfig(
        dry_run=False,
        smtp_username="sender@gmail.com",
        smtp_password="app_password_1234",
        email_from="sender@gmail.com",
        smtp_allowed_recipients=(),  # Empty
    )
    res = GmailSMTPTransport.send(sample_prepared_email, empty_allowlist_config)
    assert res.status == "failed"
    assert "not in the live-send allowlist" in res.error_message


# 6. Live sending refuses recipients not on the allowlist
def test_live_sending_refuses_unauthorized_recipient(sample_prepared_email):
    restricted_config = AppConfig(
        dry_run=False,
        smtp_username="sender@gmail.com",
        smtp_password="app_password_1234",
        email_from="sender@gmail.com",
        smtp_allowed_recipients=("someone_else@example.com",),
    )
    res = GmailSMTPTransport.send(sample_prepared_email, restricted_config)
    assert res.status == "failed"
    assert "not in the live-send allowlist" in res.error_message


# 7. Allowlisted recipients can reach the mocked SMTP transport
def test_allowlisted_recipient_reaches_smtp_transport(mock_config_live, sample_prepared_email):
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_instance = MagicMock()
        mock_smtp_cls.return_value = mock_instance

        res = GmailSMTPTransport.send(sample_prepared_email, mock_config_live)
        assert res.status == "sent"
        assert res.error_message is None
        mock_smtp_cls.assert_called_once_with("smtp.gmail.com", 587, timeout=30)
        assert mock_instance.send_message.called


# 8. STARTTLS is invoked before authentication
def test_starttls_invoked_before_authentication(mock_config_live, sample_prepared_email):
    call_log = []

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_instance = MagicMock()
        mock_instance.starttls.side_effect = lambda **kwargs: call_log.append("starttls")
        mock_instance.login.side_effect = lambda u, p: call_log.append("login")
        mock_instance.send_message.side_effect = lambda msg: call_log.append("send_message")
        mock_smtp_cls.return_value = mock_instance

        res = GmailSMTPTransport.send(sample_prepared_email, mock_config_live)
        assert res.status == "sent"
        assert call_log == ["starttls", "login", "send_message"]


# 9. MIME messages contain both plain-text and HTML alternatives
def test_mime_message_structure(mock_config_live, sample_prepared_email):
    msg = build_mime_message(sample_prepared_email, mock_config_live)
    assert isinstance(msg, EmailMessage)
    assert msg.is_multipart()
    
    # Check parts
    parts = list(msg.iter_parts())
    assert len(parts) == 2
    types = {p.get_content_type() for p in parts}
    assert types == {"text/plain", "text/html"}


# 10. Sender and recipient headers are correct
def test_sender_and_recipient_headers(mock_config_live, sample_prepared_email):
    msg = build_mime_message(sample_prepared_email, mock_config_live)
    assert msg["To"] == "authorized_user@example.com"
    assert "Akash Das Dispatcher" in msg["From"]
    assert "test_sender@gmail.com" in msg["From"]
    assert msg["Subject"] == sample_prepared_email.subject


# 11. SMTP authentication failures are handled safely
def test_smtp_authentication_failure_handled_safely(mock_config_live, sample_prepared_email):
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_instance = MagicMock()
        mock_instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication credentials invalid")
        mock_smtp_cls.return_value = mock_instance

        res = GmailSMTPTransport.send(sample_prepared_email, mock_config_live)
        assert res.status == "failed"
        assert "SMTP Authentication failed" in res.error_message
        assert mock_config_live.smtp_password not in res.error_message


# 12. Definite SMTP failures are marked failed
def test_definite_smtp_failures_marked_failed(mock_config_live, sample_prepared_email):
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_instance = MagicMock()
        mock_instance.send_message.side_effect = smtplib.SMTPRecipientsRefused({"user@example.com": (550, b"User unknown")})
        mock_smtp_cls.return_value = mock_instance

        res = GmailSMTPTransport.send(sample_prepared_email, mock_config_live)
        assert res.status == "failed"
        assert "Definitive SMTP transmission error" in res.error_message


# 13. Ambiguous transmission failures are marked delivery_unknown
def test_ambiguous_transmission_failure_marked_delivery_unknown(mock_config_live, sample_prepared_email):
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_instance = MagicMock()
        # Simulate network drop during send_message payload transmission
        mock_instance.send_message.side_effect = socket.timeout("timed out writing payload")
        mock_smtp_cls.return_value = mock_instance

        res = GmailSMTPTransport.send(sample_prepared_email, mock_config_live)
        assert res.status == "delivery_unknown"
        assert "Ambiguous transmission outcome" in res.error_message


# 14. delivery_unknown records are not automatically retried
def test_delivery_unknown_records_not_automatically_retried(temp_db: Path, sample_prepared_email, mock_config_live):
    seed_ready_reminder(temp_db, sample_prepared_email)

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_instance = MagicMock()
        mock_instance.send_message.side_effect = socket.timeout("connection dropped")
        mock_smtp_cls.return_value = mock_instance

        # First dispatch -> delivery_unknown
        summary1 = dispatch_ready_emails(temp_db, config=mock_config_live, confirm_live_send=True)
        assert summary1.delivery_unknown == 1

        with get_db_connection(temp_db) as conn:
            status = conn.execute("SELECT status FROM reminders WHERE reminder_id='REM001';").fetchone()[0]
            assert status == "delivery_unknown"

        # Subsequent dispatch cycle -> should NOT claim delivery_unknown record!
        summary2 = dispatch_ready_emails(temp_db, config=mock_config_live, confirm_live_send=True)
        assert summary2.claimed == 0
        assert summary2.delivery_unknown == 0


# 15. Two concurrent dispatchers cannot claim the same record
def test_concurrent_dispatchers_claim_exclusivity(temp_db: Path, sample_prepared_email):
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute("INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);", (now_str,))
            for i in range(10):
                conn.execute(
                    f"INSERT INTO reminders VALUES ('REM_DISP_{i}', 'CON001', 'Task', 'deadline', ?, 'ready', 'REF', 'Note', NULL, ?, ?);",
                    (now_str, now_str, now_str),
                )
                conn.execute(
                    f"""
                    INSERT INTO prepared_emails VALUES (
                        'REM_DISP_{i}', 'CON001', 'a@example.com', 'Aarav Sharma',
                        'deadline', 'Subj', '<p>H</p>', 'T', ?, 'REF', ?
                    );
                    """,
                    (now_str, now_str),
                )

    config = AppConfig(dry_run=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(dispatch_ready_emails, temp_db, config)
        f2 = executor.submit(dispatch_ready_emails, temp_db, config)
        r1 = f1.result()
        r2 = f2.result()

    total_simulated = r1.simulated + r2.simulated
    assert total_simulated == 10
    with get_db_connection(temp_db) as conn:
        sim_count = conn.execute("SELECT count(*) FROM reminders WHERE status = 'simulated';").fetchone()[0]
        assert sim_count == 10


# 16. Database state remains consistent after failures
def test_database_state_consistent_after_failure(temp_db: Path, sample_prepared_email, mock_config_live):
    seed_ready_reminder(temp_db, sample_prepared_email)

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_instance = MagicMock()
        mock_instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")
        mock_smtp_cls.return_value = mock_instance

        summary = dispatch_ready_emails(temp_db, config=mock_config_live, confirm_live_send=True)
        assert summary.failed == 1

        with get_db_connection(temp_db) as conn:
            row = conn.execute("SELECT status, dispatch_error FROM reminders WHERE reminder_id='REM001';").fetchone()
            assert row["status"] == "failed"
            assert "SMTP Authentication failed" in row["dispatch_error"]


# 17. No credentials appear in logs or exception summaries
def test_no_credentials_in_logs_or_exceptions(sample_prepared_email, mock_config_live):
    secret_pw = mock_config_live.smtp_password
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_instance = MagicMock()
        mock_instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Wrong password")
        mock_smtp_cls.return_value = mock_instance

        res = GmailSMTPTransport.send(sample_prepared_email, mock_config_live)
        assert secret_pw not in str(res.error_message)


# 18. Batch dispatch summary counts match exactly
def test_batch_dispatch_summary_metrics(temp_db: Path):
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute("INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);", (now_str,))
            for i in range(5):
                conn.execute(
                    f"INSERT INTO reminders VALUES ('REM_BATCH_{i}', 'CON001', 'Task', 'deadline', ?, 'ready', 'REF', 'Note', NULL, ?, ?);",
                    (now_str, now_str, now_str),
                )
                conn.execute(
                    f"INSERT INTO prepared_emails VALUES ('REM_BATCH_{i}', 'CON001', 'a@example.com', 'Aarav', 'deadline', 'Sub', 'H', 'T', ?, 'R', ?);",
                    (now_str, now_str),
                )

    summary = dispatch_ready_emails(temp_db, config=AppConfig(dry_run=True))
    assert summary.examined == 5
    assert summary.claimed == 5
    assert summary.simulated == 5
    assert summary.smtp_accepted == 0
    assert summary.failed == 0
    assert summary.delivery_unknown == 0
    assert len(summary.processed_ids) == 5


# ==============================================================================
# PHASE 8 FINAL DISPATCH RELIABILITY AUDIT TESTS
# ==============================================================================

# 19. Interrupted processing recovery and safe reconciliation
def test_interrupted_processing_recovery(temp_db: Path, sample_prepared_email):
    """Simulates application crash during dispatch leaving records in 'processing'.
    Verifies they are discovered, never auto-retried, and safely reconciled.
    """
    seed_ready_reminder(temp_db, sample_prepared_email)
    
    # Transition manually to 'processing' to simulate mid-dispatch sudden termination
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute("UPDATE reminders SET status = 'processing' WHERE reminder_id = 'REM001';")

    # 1. Discover stranded records
    stale_records = get_stale_processing_reminders(temp_db)
    assert len(stale_records) == 1
    assert stale_records[0].reminder_id == "REM001"
    assert stale_records[0].status == "processing"

    # 2. Standard dispatcher NEVER automatically claims or re-runs processing records
    summary = dispatch_ready_emails(temp_db, config=AppConfig(dry_run=True))
    assert summary.examined == 0
    assert summary.claimed == 0

    # 3. Attempting to force status back to 'ready' without allow_ready_retry raises ValueError
    with pytest.raises(ValueError, match="Returning 'processing' records to 'ready' is unsafe"):
        reconcile_stale_processing_records(temp_db, target_status="ready", allow_ready_retry=False)

    # 4. Safely reconcile to 'delivery_unknown'
    reconciled_count = reconcile_stale_processing_records(
        temp_db,
        target_status="delivery_unknown",
        reason="Operator recovery after process termination",
    )
    assert reconciled_count == 1

    with get_db_connection(temp_db) as conn:
        row = conn.execute("SELECT status, dispatch_error FROM reminders WHERE reminder_id = 'REM001';").fetchone()
        assert row["status"] == "delivery_unknown"
        assert "Operator recovery" in row["dispatch_error"]

    # 5. Delivery unknown records are never automatically retried
    sum2 = dispatch_ready_emails(temp_db, config=AppConfig(dry_run=True))
    assert sum2.examined == 0


# 20. Database failure after SMTP acceptance
def test_db_failure_after_smtp_acceptance(monkeypatch, temp_db: Path, sample_prepared_email, mock_config_live):
    """Simulates message acceptance by SMTP followed by SQLite failure when saving 'sent' status.
    Verifies message is treated conservatively as delivery_unknown and never marked safely retryable.
    """
    seed_ready_reminder(temp_db, sample_prepared_email)

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_instance = MagicMock()
        mock_smtp_cls.return_value = mock_instance

        import sqlite3
        import email_automation.mailer as mailer_module

        orig_update = mailer_module.update_dispatch_outcome

        def failing_update_outcome(db_path, reminder_id, new_status, error_message=None):
            if new_status == "sent":
                # Primary update to 'sent' fails (e.g. disk full, lock timeout)
                raise sqlite3.OperationalError("Simulated DB lock/disk failure after SMTP 250 OK")
            return orig_update(db_path, reminder_id, new_status, error_message)

        monkeypatch.setattr(mailer_module, "update_dispatch_outcome", failing_update_outcome)

        summary = dispatch_ready_emails(temp_db, config=mock_config_live, confirm_live_send=True)
        assert summary.examined == 1
        assert summary.claimed == 1
        assert summary.smtp_accepted == 0  # Not counted as accepted because DB record failed
        assert summary.delivery_unknown == 1
        assert any("CRITICAL: Message was accepted by SMTP server" in err for err in summary.errors)

        # Database must record delivery_unknown, NEVER ready or pending
        with get_db_connection(temp_db) as conn:
            row = conn.execute("SELECT status, dispatch_error FROM reminders WHERE reminder_id = 'REM001';").fetchone()
            assert row["status"] == "delivery_unknown"
            assert "accepted by SMTP server, but database update to 'sent' failed" in row["dispatch_error"]

        # Subsequent dispatch run must not touch or retry this record
        sum2 = dispatch_ready_emails(temp_db, config=mock_config_live, confirm_live_send=True)
        assert sum2.examined == 0


# 21. Phase 7 to Phase 8 schema migration preserving existing records
def test_phase7_to_phase8_schema_migration(tmp_path: Path):
    """Creates a database strictly on the Phase 7 schema and verifies lossless upgrade to Phase 8."""
    import sqlite3
    db_file = tmp_path / "phase7_legacy.db"

    now_str = datetime.now(timezone.utc).isoformat()

    # 1. Create exact Phase 7 schema (10 columns in reminders, no dispatch_error, strict CHECK)
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
                status TEXT NOT NULL CHECK(status IN ('pending', 'ready', 'processing', 'sent', 'failed')),
                reference_id TEXT NOT NULL,
                notes TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (contact_id) REFERENCES contacts (contact_id) ON DELETE CASCADE
            );

            CREATE INDEX idx_reminders_status_due ON reminders (status, due_at);

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
            """
        )

        # Insert sample contacts
        conn.execute("INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'aarav@example.com', 'IT', 'Apex', ?);", (now_str,))
        conn.execute("INSERT INTO contacts VALUES ('CON002', 'Diya', 'Patel', 'diya@example.com', 'Finance', 'Apex', ?);", (now_str,))

        # Insert sample reminders with different statuses
        conn.execute("INSERT INTO reminders VALUES ('REM001', 'CON001', 'Meeting', 'meeting', ?, 'pending', 'M-1', 'Note 1', ?, ?);", (now_str, now_str, now_str))
        conn.execute("INSERT INTO reminders VALUES ('REM002', 'CON001', 'Payment', 'payment', ?, 'ready', 'P-1', 'Note 2', ?, ?);", (now_str, now_str, now_str))
        conn.execute("INSERT INTO reminders VALUES ('REM003', 'CON002', 'Deadline', 'deadline', ?, 'sent', 'D-1', 'Note 3', ?, ?);", (now_str, now_str, now_str))

        # Insert prepared email for REM002
        conn.execute(
            """
            INSERT INTO prepared_emails VALUES (
                'REM002', 'CON001', 'aarav@example.com', 'Aarav Sharma',
                'payment', 'Payment Notice', '<p>Pay</p>', 'Pay', ?, 'P-1', ?
            );
            """,
            (now_str, now_str),
        )

    # Verify that in Phase 7 schema, status='simulated' or 'delivery_unknown' is rejected
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("UPDATE reminders SET status = 'simulated' WHERE reminder_id = 'REM001';")

    conn.close()

    # 2. Execute migration to Phase 8
    applied = migrate_db(db_file)
    assert applied is True

    # 3. Verify data preservation
    with get_db_connection(db_file) as conn:
        # Contacts preserved
        contacts = conn.execute("SELECT * FROM contacts ORDER BY contact_id;").fetchall()
        assert len(contacts) == 2
        assert contacts[0]["contact_id"] == "CON001"
        assert contacts[1]["contact_id"] == "CON002"

        # Reminders preserved with original statuses
        rems = conn.execute("SELECT reminder_id, status, dispatch_error FROM reminders ORDER BY reminder_id;").fetchall()
        assert len(rems) == 3
        assert rems[0]["reminder_id"] == "REM001" and rems[0]["status"] == "pending" and rems[0]["dispatch_error"] is None
        assert rems[1]["reminder_id"] == "REM002" and rems[1]["status"] == "ready" and rems[1]["dispatch_error"] is None
        assert rems[2]["reminder_id"] == "REM003" and rems[2]["status"] == "sent" and rems[2]["dispatch_error"] is None

        # Prepared email content preserved
        preps = conn.execute("SELECT * FROM prepared_emails;").fetchall()
        assert len(preps) == 1
        assert preps[0]["reminder_id"] == "REM002"
        assert preps[0]["subject"] == "Payment Notice"
        assert preps[0]["html_body"] == "<p>Pay</p>"

        # Foreign key integrity check
        fk_check = conn.execute("PRAGMA foreign_key_check;").fetchall()
        assert len(fk_check) == 0

        # Phase 8 statuses 'simulated' and 'delivery_unknown' are now valid
        with conn:
            conn.execute("UPDATE reminders SET status = 'simulated' WHERE reminder_id = 'REM001';")
            conn.execute("UPDATE reminders SET status = 'delivery_unknown', dispatch_error = 'Test err' WHERE reminder_id = 'REM002';")

        r1 = conn.execute("SELECT status FROM reminders WHERE reminder_id = 'REM001';").fetchone()
        r2 = conn.execute("SELECT status, dispatch_error FROM reminders WHERE reminder_id = 'REM002';").fetchone()
        assert r1["status"] == "simulated"
        assert r2["status"] == "delivery_unknown"
        assert r2["dispatch_error"] == "Test err"

    # 4. Second migration call is idempotent (returns False)
    assert migrate_db(db_file) is False


# 22. SMTP Result Classification Matrix
def test_smtp_result_classification_matrix(sample_prepared_email, mock_config_live):
    """Verifies precise classification of SMTP exception types without broad catch-all assumptions."""
    # 1. SMTPAuthenticationError -> failed
    with patch("smtplib.SMTP") as mock_cls:
        inst = MagicMock()
        inst.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failure")
        mock_cls.return_value = inst
        res = GmailSMTPTransport.send(sample_prepared_email, mock_config_live)
        assert res.status == "failed"
        assert "Authentication failed" in res.error_message

    # 2. SMTPRecipientsRefused -> failed
    with patch("smtplib.SMTP") as mock_cls:
        inst = MagicMock()
        inst.send_message.side_effect = smtplib.SMTPRecipientsRefused({"user@example.com": (550, b"User not found")})
        mock_cls.return_value = inst
        res = GmailSMTPTransport.send(sample_prepared_email, mock_config_live)
        assert res.status == "failed"
        assert "Definitive SMTP transmission error" in res.error_message

    # 3. SMTPConnectError (before transmission) -> failed
    with patch("smtplib.SMTP") as mock_cls:
        mock_cls.side_effect = smtplib.SMTPConnectError(421, b"Connection refused")
        res = GmailSMTPTransport.send(sample_prepared_email, mock_config_live)
        assert res.status == "failed"
        assert "Definitive SMTP connection failure" in res.error_message

    # 4. SMTPServerDisconnected after send initiated -> delivery_unknown
    with patch("smtplib.SMTP") as mock_cls:
        inst = MagicMock()
        inst.send_message.side_effect = smtplib.SMTPServerDisconnected("Connection lost post-DATA")
        mock_cls.return_value = inst
        res = GmailSMTPTransport.send(sample_prepared_email, mock_config_live)
        assert res.status == "delivery_unknown"
        assert "Ambiguous transmission outcome" in res.error_message

    # 5. socket.timeout after send initiated -> delivery_unknown
    with patch("smtplib.SMTP") as mock_cls:
        inst = MagicMock()
        inst.send_message.side_effect = socket.timeout("Timed out waiting for 250 OK")
        mock_cls.return_value = inst
        res = GmailSMTPTransport.send(sample_prepared_email, mock_config_live)
        assert res.status == "delivery_unknown"
        assert "Ambiguous transmission outcome" in res.error_message


# 23. Ambiguous and non-ready records are never automatically retried
def test_ambiguous_and_non_ready_records_never_auto_retried(temp_db: Path):
    """Ensures that records in 'delivery_unknown', 'failed', 'simulated', or 'processing' are never claimed."""
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(temp_db) as conn:
        with conn:
            conn.execute("INSERT INTO contacts VALUES ('CON001', 'Aarav', 'Sharma', 'a@example.com', 'IT', 'Apex', ?);", (now_str,))
            statuses = ["delivery_unknown", "failed", "simulated", "processing"]
            for i, st in enumerate(statuses):
                conn.execute(
                    f"INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, dispatch_error, created_at, updated_at) VALUES ('REM_ST_{i}', 'CON001', 'Task', 'deadline', ?, ?, 'REF', 'Note', 'Error info', ?, ?);",
                    (now_str, st, now_str, now_str),
                )
                conn.execute(
                    f"INSERT INTO prepared_emails VALUES ('REM_ST_{i}', 'CON001', 'a@example.com', 'Aarav', 'deadline', 'Sub', 'H', 'T', ?, 'R', ?);",
                    (now_str, now_str),
                )

    # Dry-run dispatch should examine 0 ready records
    summary = dispatch_ready_emails(temp_db, config=AppConfig(dry_run=True))
    assert summary.examined == 0
    assert summary.claimed == 0
    assert summary.simulated == 0

    # Reminders retain their exact original statuses
    with get_db_connection(temp_db) as conn:
        rows = conn.execute("SELECT reminder_id, status FROM reminders ORDER BY reminder_id;").fetchall()
        for i, st in enumerate(statuses):
            assert rows[i]["status"] == st
