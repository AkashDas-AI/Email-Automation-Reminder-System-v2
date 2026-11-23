"""Database Management Module

Author: Akash Das
Responsibility: Centralized SQLite connection management, table initialization, and transactional CRUD operations.
"""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

from .models import ActivityLog, Contact, PersonalizedEmail, Reminder

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/database/reminders.db")


@contextmanager
def get_db_connection(db_path: Union[Path, str] = DEFAULT_DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    """Yields a managed SQLite connection configured with WAL mode, busy timeout, and foreign key enforcement."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    try:
        yield conn
    finally:
        conn.close()


def migrate_db(db_path: Union[Path, str] = DEFAULT_DB_PATH) -> bool:
    """Migrates an existing database to the current schema (Phase 9) if needed.
    
    Guarantees:
        - Contacts, reminders, and prepared_emails are strictly preserved.
        - Existing reminder statuses and email content remain intact.
        - Adds dispatch_error column and updates status CHECK constraint (Phase 7 -> Phase 8).
        - Creates activity_logs table and performance indexes (Phase 8 -> Phase 9).
        - Tracks schema versioning in schema_version table.
    
    Returns:
        bool: True if migration was applied; False if already up-to-date.
    """
    path = Path(db_path)
    if not path.is_file():
        return False

    with get_db_connection(db_path) as conn:
        # Check if reminders table exists
        cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='reminders';")
        row = cursor.fetchone()
        if not row:
            return False

        table_sql = row[0] or ""
        
        # Check schema version table if present
        v_cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version';")
        has_version_tbl = bool(v_cursor.fetchone())
        current_version = 0
        if has_version_tbl:
            ver_row = conn.execute("SELECT max(version) FROM schema_version;").fetchone()
            current_version = ver_row[0] if ver_row and ver_row[0] else 0

        # 1. Inspect Reminders compliance
        cols_cursor = conn.execute("PRAGMA table_info(reminders);")
        col_names = {c["name"] for c in cols_cursor.fetchall()}
        has_dispatch_error = "dispatch_error" in col_names
        has_simulated = "'simulated'" in table_sql
        has_delivery_unknown = "'delivery_unknown'" in table_sql
        reminders_compliant = bool(has_dispatch_error and has_simulated and has_delivery_unknown)

        # 2. Inspect Activity Logs compliance
        act_cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='activity_logs';")
        has_activity_logs = bool(act_cursor.fetchone())
        act_complete = False
        if has_activity_logs:
            act_cols = {c["name"] for c in conn.execute("PRAGMA table_info(activity_logs);").fetchall()}
            required_cols = {"log_id", "timestamp", "event_type", "severity", "reminder_id", "contact_id", "status", "message", "details"}
            act_complete = required_cols.issubset(act_cols)

        # If already fully migrated and version is at least 9, no work needed
        if current_version >= 9 and reminders_compliant and act_complete:
            return False

        migration_performed = False

        # 1. Reminders schema migration (Phase 7 -> Phase 8)
        if not reminders_compliant:
            logger.info("Migrating database at %s from Phase 7 to Phase 8 schema...", path)
            conn.execute("PRAGMA foreign_keys = OFF;")
            with conn:
                conn.execute(
                    """
                    CREATE TABLE _reminders_phase8 (
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
                    """
                )
                
                dispatch_col_sql = "dispatch_error" if "dispatch_error" in col_names else "NULL AS dispatch_error"

                conn.execute(
                    f"""
                    INSERT INTO _reminders_phase8 (
                        reminder_id, contact_id, reminder_type, template_key,
                        due_at, status, reference_id, notes, dispatch_error,
                        created_at, updated_at
                    )
                    SELECT
                        reminder_id, contact_id, reminder_type, template_key,
                        due_at, status, reference_id, notes, {dispatch_col_sql},
                        created_at, updated_at
                    FROM reminders;
                    """
                )
                
                conn.execute("DROP TABLE reminders;")
                conn.execute("ALTER TABLE _reminders_phase8 RENAME TO reminders;")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_status_due ON reminders (status, due_at);")

            conn.execute("PRAGMA foreign_keys = ON;")
            fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
            if fk_violations:
                raise sqlite3.IntegrityError(f"Foreign key integrity violated during migration: {fk_violations}")
            migration_performed = True

        # 2. Activity logs migration (Phase 8 -> Phase 9)
        act_cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='activity_logs';")
        has_activity_logs = bool(act_cursor.fetchone())

        needs_act_migration = False
        if not has_activity_logs or current_version < 9:
            needs_act_migration = True
        elif has_activity_logs:
            act_cols = {c["name"] for c in conn.execute("PRAGMA table_info(activity_logs);").fetchall()}
            required_cols = {"log_id", "timestamp", "event_type", "severity", "reminder_id", "contact_id", "status", "message", "details"}
            if not required_cols.issubset(act_cols):
                needs_act_migration = True

        if needs_act_migration:
            logger.info("Migrating database at %s to Phase 9 schema (activity_logs)...", path)
            with conn:
                if has_activity_logs:
                    act_cols = {c["name"] for c in conn.execute("PRAGMA table_info(activity_logs);").fetchall()}
                    required_cols = {"log_id", "timestamp", "event_type", "severity", "reminder_id", "contact_id", "status", "message", "details"}
                    if not required_cols.issubset(act_cols):
                        id_col = "log_id" if "log_id" in act_cols else "id"
                        if "status" in act_cols:
                            status_col = "status"
                        else:
                            status_col = """
                                CASE
                                    WHEN event_type IN ('reminder_prepared', 'reminder_ready') THEN 'ready'
                                    WHEN event_type IN ('reminder_preparation_failed', 'email_failed') THEN 'failed'
                                    WHEN event_type = 'email_simulated' THEN 'simulated'
                                    WHEN event_type = 'email_smtp_accepted' THEN 'sent'
                                    WHEN event_type = 'email_delivery_unknown' THEN 'delivery_unknown'
                                    ELSE 'recorded'
                                END AS status
                            """

                        if "message" in act_cols:
                            msg_col = "message"
                        else:
                            msg_col = "coalesce(event_type, 'Historical activity event') AS message"

                        if "details" in act_cols:
                            details_col = "details"
                        elif "details_json" in act_cols:
                            details_col = "details_json AS details"
                        else:
                            details_col = "NULL AS details"

                        conn.execute(
                            """
                            CREATE TABLE _activity_logs_v9 (
                                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                                timestamp TEXT NOT NULL,
                                event_type TEXT NOT NULL,
                                severity TEXT NOT NULL,
                                reminder_id TEXT,
                                contact_id TEXT,
                                status TEXT NOT NULL,
                                message TEXT NOT NULL,
                                details TEXT
                            );
                            """
                        )
                        conn.execute(
                            f"""
                            INSERT INTO _activity_logs_v9 (log_id, timestamp, event_type, severity, reminder_id, contact_id, status, message, details)
                            SELECT {id_col}, timestamp, event_type, severity, reminder_id, contact_id, {status_col}, {msg_col}, {details_col}
                            FROM activity_logs;
                            """
                        )
                        conn.execute("DROP TABLE activity_logs;")
                        conn.execute("ALTER TABLE _activity_logs_v9 RENAME TO activity_logs;")
                else:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS activity_logs (
                            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            timestamp TEXT NOT NULL,
                            event_type TEXT NOT NULL,
                            severity TEXT NOT NULL,
                            reminder_id TEXT,
                            contact_id TEXT,
                            status TEXT NOT NULL,
                            message TEXT NOT NULL,
                            details TEXT
                        );
                        """
                    )

                conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_logs_ts ON activity_logs (timestamp);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_logs_event ON activity_logs (event_type);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_logs_severity ON activity_logs (severity);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_logs_reminder ON activity_logs (reminder_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_logs_status ON activity_logs (status);")

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_version (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    );
                    """
                )
                now_iso = datetime.now(timezone.utc).isoformat()
                conn.execute("INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (9, ?);", (now_iso,))
            migration_performed = True

        fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
        if fk_violations:
            raise sqlite3.IntegrityError(f"Foreign key integrity violated: {fk_violations}")

        if migration_performed:
            log_activity(
                db_path=path,
                event_type="database_migrated",
                severity="INFO",
                status="success",
                message=f"Database schema migrated successfully to version 9 at {path}",
                details={"schema_version": 9, "path": str(path)},
            )

        return migration_performed


def init_db(db_path: Union[Path, str] = DEFAULT_DB_PATH) -> None:
    """Creates the SQLite database tables and indexes if they do not already exist,
    or safely upgrades existing tables to the current Phase 9 schema."""
    path = Path(db_path)
    if path.is_file():
        migrate_db(db_path)

    with get_db_connection(db_path) as conn:
        with conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS contacts (
                    contact_id TEXT PRIMARY KEY,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    department TEXT NOT NULL,
                    company TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reminders (
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

                CREATE INDEX IF NOT EXISTS idx_reminders_status_due ON reminders (status, due_at);

                CREATE TABLE IF NOT EXISTS prepared_emails (
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

                CREATE TABLE IF NOT EXISTS activity_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    reminder_id TEXT,
                    contact_id TEXT,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_activity_logs_ts ON activity_logs (timestamp);
                CREATE INDEX IF NOT EXISTS idx_activity_logs_event ON activity_logs (event_type);
                CREATE INDEX IF NOT EXISTS idx_activity_logs_severity ON activity_logs (severity);
                CREATE INDEX IF NOT EXISTS idx_activity_logs_reminder ON activity_logs (reminder_id);
                CREATE INDEX IF NOT EXISTS idx_activity_logs_status ON activity_logs (status);

                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (9, datetime('now'));
                """
            )

    log_activity(
        db_path=db_path,
        event_type="database_initialized",
        severity="INFO",
        status="success",
        message=f"Database initialized/verified successfully at {db_path}",
        details={"path": str(db_path)},
    )


def import_or_sync_csv(
    db_path: Union[Path, str],
    contacts_csv: Union[Path, str] = "data/sample/contacts.csv",
    reminders_csv: Union[Path, str] = "data/sample/reminders.csv",
) -> Tuple[int, int]:
    """Imports or synchronizes contacts and reminders from CSV files idempotently.
    
    Returns:
        Tuple[int, int]: (contacts_synced, reminders_synced)
    """
    init_db(db_path)
    now_str = datetime.now(timezone.utc).isoformat()
    
    contacts_path = Path(contacts_csv)
    reminders_path = Path(reminders_csv)

    if not contacts_path.is_file():
        raise FileNotFoundError(f"Contacts CSV not found: {contacts_path}")
    if not reminders_path.is_file():
        raise FileNotFoundError(f"Reminders CSV not found: {reminders_path}")

    contacts_synced = 0
    reminders_synced = 0

    with get_db_connection(db_path) as conn:
        with conn:
            # 1. Sync Contacts
            with open(contacts_path, mode="r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    conn.execute(
                        """
                        INSERT INTO contacts (contact_id, first_name, last_name, email, department, company, created_at)
                        VALUES (:contact_id, :first_name, :last_name, :email, :department, :company, :created_at)
                        ON CONFLICT(contact_id) DO UPDATE SET
                            first_name=excluded.first_name,
                            last_name=excluded.last_name,
                            email=excluded.email,
                            department=excluded.department,
                            company=excluded.company;
                        """,
                        {
                            "contact_id": row["contact_id"].strip(),
                            "first_name": row["first_name"].strip(),
                            "last_name": row["last_name"].strip(),
                            "email": row["email"].strip(),
                            "department": row["department"].strip(),
                            "company": row["company"].strip(),
                            "created_at": now_str,
                        },
                    )
                    contacts_synced += 1

            # 2. Sync Reminders
            with open(reminders_path, mode="r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # If reminder already exists in 'ready', 'processing', 'sent', etc.,
                    # preserve its active operational lifecycle status; only update metadata.
                    conn.execute(
                        """
                        INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, dispatch_error, created_at, updated_at)
                        VALUES (:reminder_id, :contact_id, :reminder_type, :template_key, :due_at, :status, :reference_id, :notes, NULL, :created_at, :updated_at)
                        ON CONFLICT(reminder_id) DO UPDATE SET
                            reminder_type=excluded.reminder_type,
                            template_key=excluded.template_key,
                            due_at=excluded.due_at,
                            reference_id=excluded.reference_id,
                            notes=excluded.notes,
                            updated_at=excluded.updated_at
                        WHERE reminders.status = 'pending';
                        """,
                        {
                            "reminder_id": row["reminder_id"].strip(),
                            "contact_id": row["contact_id"].strip(),
                            "reminder_type": row["reminder_type"].strip(),
                            "template_key": row["template_key"].strip(),
                            "due_at": row["due_at"].strip(),
                            "status": row.get("status", "pending").strip() or "pending",
                            "reference_id": row.get("reference_id", "").strip(),
                            "notes": row["notes"].strip(),
                            "created_at": now_str,
                            "updated_at": now_str,
                        },
                    )
                    reminders_synced += 1

    log_activity(
        db_path=db_path,
        event_type="data_synced",
        severity="INFO",
        status="success",
        message=f"Synchronized {contacts_synced} contacts and {reminders_synced} reminders from CSV.",
        details={"contacts_synced": contacts_synced, "reminders_synced": reminders_synced},
    )

    return contacts_synced, reminders_synced


def get_contact_by_id(db_path: Union[Path, str], contact_id: str) -> Optional[Contact]:
    """Retrieves a Contact entity by its primary key."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT contact_id, first_name, last_name, email, department, company FROM contacts WHERE contact_id = ?;",
            (contact_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Contact(
            contact_id=row["contact_id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            email=row["email"],
            department=row["department"],
            company=row["company"],
        )


def get_pending_reminders(db_path: Union[Path, str]) -> List[Reminder]:
    """Retrieves all reminders currently in 'pending' status."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes
            FROM reminders
            WHERE status = 'pending'
            ORDER BY due_at ASC;
            """
        )
        return [
            Reminder(
                reminder_id=row["reminder_id"],
                contact_id=row["contact_id"],
                reminder_type=row["reminder_type"],
                template_key=row["template_key"],
                due_at=row["due_at"],
                status=row["status"],
                reference_id=row["reference_id"],
                notes=row["notes"],
            )
            for row in cursor.fetchall()
        ]


def transition_reminder_to_ready(
    db_path: Union[Path, str],
    reminder_id: str,
    prepared_email: PersonalizedEmail,
) -> bool:
    """Atomically transitions a reminder from 'pending' to 'ready' and records its prepared email payload.
    
    Returns:
        bool: True if transition succeeded; False if reminder was already claimed/transitioned by another worker.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(db_path) as conn:
        with conn:
            # 1. Atomic claim check
            cursor = conn.execute(
                """
                UPDATE reminders
                SET status = 'ready', updated_at = ?
                WHERE reminder_id = ? AND status = 'pending';
                """,
                (now_str, reminder_id),
            )
            if cursor.rowcount == 0:
                # Another worker or process already claimed this reminder or it is no longer pending
                return False

            # 2. Persist prepared email payload within the exact same transaction
            conn.execute(
                """
                INSERT INTO prepared_emails (
                    reminder_id, contact_id, recipient_email, recipient_name,
                    template_key, subject, html_body, text_body, due_at, reference_id, prepared_at
                ) VALUES (
                    :reminder_id, :contact_id, :recipient_email, :recipient_name,
                    :template_key, :subject, :html_body, :text_body, :due_at, :reference_id, :prepared_at
                );
                """,
                {
                    "reminder_id": prepared_email.reminder_id,
                    "contact_id": prepared_email.contact_id,
                    "recipient_email": prepared_email.recipient_email,
                    "recipient_name": prepared_email.recipient_name,
                    "template_key": prepared_email.template_key,
                    "subject": prepared_email.subject,
                    "html_body": prepared_email.html_body,
                    "text_body": prepared_email.text_body,
                    "due_at": prepared_email.due_at,
                    "reference_id": prepared_email.reference_id,
                    "prepared_at": now_str,
                },
            )

            # Record activity history
            try:
                conn.execute(
                    """
                    INSERT INTO activity_logs (
                        timestamp, event_type, severity, reminder_id, contact_id, status, message, details
                    ) VALUES (?, 'reminder_prepared', 'INFO', ?, ?, 'ready', ?, ?);
                    """,
                    (
                        now_str,
                        reminder_id,
                        prepared_email.contact_id,
                        f"Reminder {reminder_id} prepared successfully with template '{prepared_email.template_key}'.",
                        json.dumps({"recipient_email": prepared_email.recipient_email, "subject": prepared_email.subject}),
                    ),
                )
            except Exception as e:
                logger.warning("Could not log activity in transition_reminder_to_ready: %s", e)

            return True


def get_all_prepared_emails(db_path: Union[Path, str] = DEFAULT_DB_PATH) -> List[PersonalizedEmail]:
    """Retrieves all prepared email records currently marked ready for dispatch in Phase 8."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT p.reminder_id, p.contact_id, p.recipient_email, p.recipient_name,
                   p.template_key, p.subject, p.html_body, p.text_body, p.due_at, p.reference_id
            FROM prepared_emails p
            JOIN reminders r ON p.reminder_id = r.reminder_id
            WHERE r.status = 'ready'
            ORDER BY p.due_at ASC;
            """
        )
        return [
            PersonalizedEmail(
                reminder_id=row["reminder_id"],
                contact_id=row["contact_id"],
                recipient_email=row["recipient_email"],
                recipient_name=row["recipient_name"],
                template_key=row["template_key"],
                subject=row["subject"],
                html_body=row["html_body"],
                text_body=row["text_body"],
                due_at=row["due_at"],
                reference_id=row["reference_id"],
            )
            for row in cursor.fetchall()
        ]


def claim_ready_emails_for_dispatch(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    limit: Optional[int] = None,
) -> List[PersonalizedEmail]:
    """Atomically claims ready reminders for dispatch by transitioning them to 'processing'.
    
    Returns:
        List[PersonalizedEmail]: Exclusively claimed prepared emails ready for transport.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    claimed: List[PersonalizedEmail] = []

    with get_db_connection(db_path) as conn:
        with conn:
            query = "SELECT reminder_id FROM reminders WHERE status = 'ready' ORDER BY due_at ASC"
            if limit is not None:
                query += f" LIMIT {int(limit)}"
            
            cursor = conn.execute(query)
            candidates = [row["reminder_id"] for row in cursor.fetchall()]

            for rem_id in candidates:
                upd = conn.execute(
                    "UPDATE reminders SET status = 'processing', updated_at = ? WHERE reminder_id = ? AND status = 'ready';",
                    (now_str, rem_id),
                )
                if upd.rowcount == 1:
                    p_row = conn.execute(
                        """
                        SELECT reminder_id, contact_id, recipient_email, recipient_name,
                               template_key, subject, html_body, text_body, due_at, reference_id
                        FROM prepared_emails
                        WHERE reminder_id = ?;
                        """,
                        (rem_id,),
                    ).fetchone()
                    if p_row:
                        claimed.append(
                            PersonalizedEmail(
                                reminder_id=p_row["reminder_id"],
                                contact_id=p_row["contact_id"],
                                recipient_email=p_row["recipient_email"],
                                recipient_name=p_row["recipient_name"],
                                template_key=p_row["template_key"],
                                subject=p_row["subject"],
                                html_body=p_row["html_body"],
                                text_body=p_row["text_body"],
                                due_at=p_row["due_at"],
                                reference_id=p_row["reference_id"],
                            )
                        )

    return claimed


def update_dispatch_outcome(
    db_path: Union[Path, str],
    reminder_id: str,
    new_status: str,
    error_message: Optional[str] = None,
) -> None:
    """Updates the final dispatch status ('simulated', 'sent', 'failed', 'delivery_unknown') and logs error text."""
    now_str = datetime.now(timezone.utc).isoformat()
    clean_err = error_message.strip() if error_message else None

    with get_db_connection(db_path) as conn:
        with conn:
            conn.execute(
                """
                UPDATE reminders
                SET status = ?, updated_at = ?, dispatch_error = ?
                WHERE reminder_id = ?;
                """,
                (new_status, now_str, clean_err, reminder_id),
            )


def get_stale_processing_reminders(db_path: Union[Path, str] = DEFAULT_DB_PATH) -> List[Reminder]:
    """Retrieves all reminders stranded in 'processing' status (e.g. following an interrupted run or crash)."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes
            FROM reminders
            WHERE status = 'processing'
            ORDER BY due_at ASC;
            """
        )
        return [
            Reminder(
                reminder_id=row["reminder_id"],
                contact_id=row["contact_id"],
                reminder_type=row["reminder_type"],
                template_key=row["template_key"],
                due_at=row["due_at"],
                status=row["status"],
                reference_id=row["reference_id"],
                notes=row["notes"],
            )
            for row in cursor.fetchall()
        ]


def reconcile_stale_processing_records(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    target_status: str = "delivery_unknown",
    reason: str = "Interrupted dispatch recovery: reconciled to prevent duplicate sending.",
    allow_ready_retry: bool = False,
) -> int:
    """Safely reconciles reminders left stranded in 'processing' status after an application crash.
    
    Guarantees:
        - By default, records are transitioned to 'delivery_unknown' or 'failed'.
        - Records are NEVER returned to 'ready' unless allow_ready_retry is explicitly True.
        - Records are NEVER automatically retried by the scheduler or dispatch pipeline.
        - Logs reconciliation reason in dispatch_error for operator audit.
        
    Returns:
        int: Number of reconciled records.
    """
    if target_status not in ("delivery_unknown", "failed", "simulated", "ready"):
        raise ValueError(f"Invalid reconciliation target_status: {target_status}")

    if target_status == "ready" and not allow_ready_retry:
        raise ValueError(
            "Returning 'processing' records to 'ready' is unsafe because messages may have already "
            "been sent to SMTP. Set allow_ready_retry=True only after human operator verification."
        )

    now_str = datetime.now(timezone.utc).isoformat()
    with get_db_connection(db_path) as conn:
        with conn:
            cursor = conn.execute(
                """
                UPDATE reminders
                SET status = ?, updated_at = ?, dispatch_error = ?
                WHERE status = 'processing';
                """,
                (target_status, now_str, reason),
            )
            reconciled = cursor.rowcount
            if reconciled > 0:
                logger.warning(
                    "Reconciled %d stale processing records to status '%s' (Reason: %s)",
                    reconciled, target_status, reason
                )
                try:
                    conn.execute(
                        """
                        INSERT INTO activity_logs (
                            timestamp, event_type, severity, reminder_id, contact_id, status, message, details
                        ) VALUES (?, 'stale_dispatch_reconciled', 'WARNING', NULL, NULL, ?, ?, ?);
                        """,
                        (
                            now_str,
                            target_status,
                            f"Reconciled {reconciled} stale processing records to status '{target_status}'. Reason: {reason}",
                            json.dumps({"reconciled_count": reconciled, "target_status": target_status, "reason": reason}),
                        ),
                    )
                except Exception as log_err:
                    logger.warning("Could not log activity in reconcile_stale_processing_records: %s", log_err)
            return reconciled


def log_activity(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    event_type: str = "general_event",
    severity: str = "INFO",
    status: str = "success",
    message: str = "",
    reminder_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    details: Optional[Union[Dict[str, Any], str]] = None,
    timestamp: Optional[str] = None,
) -> Optional[int]:
    """Persists an audit event record to the activity_logs table.
    
    Guarantees:
        - Parameterized SQL.
        - UTC ISO timestamps.
        - Structured details serialized safely as JSON.
        - Fails soft (logs warning) to ensure logging failures never corrupt core workflows.
        
    Returns:
        Optional[int]: The created log_id if successful, None otherwise.
    """
    ts_str = timestamp or datetime.now(timezone.utc).isoformat()
    clean_msg = message.strip()
    
    details_str: Optional[str] = None
    if details is not None:
        if isinstance(details, str):
            details_str = details
        else:
            try:
                details_str = json.dumps(details)
            except Exception:
                details_str = str(details)

    try:
        with get_db_connection(db_path) as conn:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO activity_logs (
                        timestamp, event_type, severity, reminder_id, contact_id, status, message, details
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        ts_str,
                        event_type.strip(),
                        severity.strip().upper(),
                        reminder_id,
                        contact_id,
                        status.strip(),
                        clean_msg,
                        details_str,
                    ),
                )
                return cursor.lastrowid
    except Exception as e:
        logger.warning("Failed to record activity log (%s: %s): %s", event_type, clean_msg, e)
        return None


def get_activity_logs(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    reminder_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[ActivityLog]:
    """Retrieves activity audit records from activity_logs with parameterized filtering.
    
    Args:
        db_path: Path to SQLite database.
        start_date: Optional start timestamp (inclusive UTC, e.g. '2026-01-01' or ISO format).
        end_date: Optional end timestamp (inclusive UTC, e.g. '2026-12-31' or ISO format).
        event_type: Optional filter by event_type.
        severity: Optional filter by severity (INFO, WARNING, ERROR, CRITICAL).
        status: Optional filter by status (e.g. 'success', 'failed', 'simulated', 'sent', etc.).
        reminder_id: Optional filter by reminder_id.
        limit: Optional maximum number of rows.
        
    Returns:
        List[ActivityLog]: Retrieved activity log records in chronological order.
    """
    conditions: List[str] = []
    params: List[Any] = []

    if start_date:
        s_str = start_date.isoformat() if isinstance(start_date, datetime) else str(start_date).strip()
        if len(s_str) == 10 and "T" not in s_str:
            s_str += "T00:00:00Z"
        conditions.append("timestamp >= ?")
        params.append(s_str)

    if end_date:
        e_str = end_date.isoformat() if isinstance(end_date, datetime) else str(end_date).strip()
        if len(e_str) == 10 and "T" not in e_str:
            e_str += "T23:59:59Z"
        conditions.append("timestamp <= ?")
        params.append(e_str)

    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type.strip())

    if severity:
        conditions.append("severity = ?")
        params.append(severity.strip().upper())

    if status:
        conditions.append("status = ?")
        params.append(status.strip())

    if reminder_id:
        conditions.append("reminder_id = ?")
        params.append(reminder_id.strip())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""

    query = f"""
        SELECT log_id, timestamp, event_type, severity, reminder_id, contact_id, status, message, details
        FROM activity_logs
        {where_clause}
        ORDER BY timestamp ASC, log_id ASC
        {limit_clause};
    """

    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        return [
            ActivityLog(
                log_id=row["log_id"],
                timestamp=row["timestamp"],
                event_type=row["event_type"],
                severity=row["severity"],
                reminder_id=row["reminder_id"],
                contact_id=row["contact_id"],
                status=row["status"],
                message=row["message"],
                details=row["details"],
            )
            for row in cursor.fetchall()
        ]
