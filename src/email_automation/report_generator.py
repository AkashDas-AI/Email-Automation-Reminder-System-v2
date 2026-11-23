"""Report Generator Module

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Generates structured, audited CSV reports capturing email activity, reminder statuses,
detailed reminder snapshots, and activity history from actual SQLite records without mock or artificial data.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Union

from .database import DEFAULT_DB_PATH, get_activity_logs, get_db_connection, log_activity
from .models import ReportResult

logger = logging.getLogger(__name__)

DEFAULT_REPORTS_DIR = Path("outputs/reports")

# Spreadsheet formula trigger characters (OWASP CSV Injection mitigation)
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_value(value: Any) -> Any:
    """Sanitizes user-controlled string values against CSV formula injection (OWASP mitigation).
    
    If the string begins with =, +, -, @, \\t, or \\r, it is prefixed with a single quote (').
    Non-string values or safe strings are returned unmodified.
    Original database values are never modified by this function.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        if value.startswith(FORMULA_PREFIXES):
            return f"'{value}"
        return value
    return value


def _get_timestamp_slug() -> str:
    """Generates a compact ISO UTC slug suitable for report filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def generate_email_activity_report(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    output_dir: Optional[Union[Path, str]] = None,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None,
) -> ReportResult:
    """Generates a CSV report documenting all email activities, prepared payloads, and dispatch outcomes.
    
    Explicitly exports:
        - reminder_id
        - contact_id
        - recipient_email
        - template_key
        - subject
        - due_at
        - dispatch_status
        - prepared_timestamp
        - dispatch_timestamp
        - safe_failure_reason
        
    Uses actual database timestamps:
        - prepared_timestamp is sourced from prepared_emails.prepared_at (empty if not prepared).
        - dispatch_timestamp is sourced from reminders.updated_at only for dispatched records
          ('simulated', 'sent', 'failed', 'delivery_unknown'), otherwise empty.
        - safe_failure_reason is sourced from reminders.dispatch_error (empty if no error).
        
    Args:
        db_path: Path to the SQLite database.
        output_dir: Target directory for the generated CSV (defaults to outputs/reports/).
        start_date: Optional filter for due_at timestamp (inclusive UTC).
        end_date: Optional filter for due_at timestamp (inclusive UTC).
        
    Returns:
        ReportResult: Structured outcome summary containing export path and record count.
    """
    out_dir = Path(output_dir) if output_dir else DEFAULT_REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = out_dir / f"email_activity_report_{_get_timestamp_slug()}.csv"
    now_iso = datetime.now(timezone.utc).isoformat()

    conditions: List[str] = [
        "r.status IN ('simulated', 'sent', 'failed', 'delivery_unknown')"
    ]
    params: List[Any] = []

    if start_date:
        s_str = start_date.isoformat() if isinstance(start_date, datetime) else str(start_date).strip()
        if len(s_str) == 10 and "T" not in s_str:
            s_str += "T00:00:00Z"
        conditions.append("r.due_at >= ?")
        params.append(s_str)

    if end_date:
        e_str = end_date.isoformat() if isinstance(end_date, datetime) else str(end_date).strip()
        if len(e_str) == 10 and "T" not in e_str:
            e_str += "T23:59:59Z"
        conditions.append("r.due_at <= ?")
        params.append(e_str)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT 
            r.reminder_id,
            r.contact_id,
            coalesce(p.recipient_email, c.email, '') AS recipient_email,
            r.template_key,
            coalesce(p.subject, '') AS subject,
            r.due_at,
            r.status AS dispatch_status,
            coalesce(p.prepared_at, '') AS prepared_timestamp,
            CASE 
                WHEN r.status IN ('simulated', 'sent', 'failed', 'delivery_unknown') THEN r.updated_at 
                ELSE '' 
            END AS dispatch_timestamp,
            coalesce(r.dispatch_error, '') AS safe_failure_reason
        FROM reminders r
        LEFT JOIN contacts c ON r.contact_id = c.contact_id
        LEFT JOIN prepared_emails p ON r.reminder_id = p.reminder_id
        {where_clause}
        ORDER BY r.due_at ASC, r.reminder_id ASC;
    """

    headers = [
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

    record_count = 0
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            with open(file_path, mode="w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for row in rows:
                    writer.writerow([
                        sanitize_csv_value(row["reminder_id"]),
                        sanitize_csv_value(row["contact_id"]),
                        sanitize_csv_value(row["recipient_email"]),
                        sanitize_csv_value(row["template_key"]),
                        sanitize_csv_value(row["subject"]),
                        sanitize_csv_value(row["due_at"]),
                        sanitize_csv_value(row["dispatch_status"]),
                        sanitize_csv_value(row["prepared_timestamp"]),
                        sanitize_csv_value(row["dispatch_timestamp"]),
                        sanitize_csv_value(row["safe_failure_reason"]),
                    ])
                    record_count += 1

        logger.info("Generated Email Activity Report at %s (%d records)", file_path, record_count)
        log_activity(
            db_path=db_path,
            event_type="report_generated",
            severity="INFO",
            status="success",
            message=f"Generated Email Activity Report ({record_count} records) to {file_path.name}",
            details={"report_type": "email_activity", "record_count": record_count, "path": str(file_path)},
        )

        return ReportResult(
            report_type="email_activity",
            file_path=file_path,
            record_count=record_count,
            generated_at=now_iso,
        )
    except Exception as err:
        logger.error("Failed to generate Email Activity Report: %s", err)
        log_activity(
            db_path=db_path,
            event_type="report_generation_failed",
            severity="ERROR",
            status="failed",
            message=f"Failed to generate Email Activity Report: {err}",
            details={"report_type": "email_activity", "error": str(err)},
        )
        raise


def generate_reminder_status_report(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    output_dir: Optional[Union[Path, str]] = None,
) -> ReportResult:
    """Generates the required Reminder Status Count Report providing counts for all 7 lifecycle states.
    
    Required Status Counts:
        - pending
        - ready
        - processing
        - simulated
        - sent (SMTP accepted)
        - failed
        - delivery_unknown
        
    Mathematical Invariants:
        - attempted = simulated + sent + failed
        - Excludes pending, ready, and processing from the attempted denominator.
        - Excludes delivery_unknown from the success-rate denominator (kept as separate operational count).
        - Keeps simulated and SMTP-accepted counts strictly separate.
        - Documents that SMTP acceptance does not confirm mailbox delivery.
        - success_rate = ((simulated + sent) / attempted * 100.0) if attempted > 0 else 0.0
    """
    out_dir = Path(output_dir) if output_dir else DEFAULT_REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = out_dir / f"reminder_status_report_{_get_timestamp_slug()}.csv"
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.execute("SELECT status, count(*) AS cnt FROM reminders GROUP BY status;")
            status_counts = {row["status"]: row["cnt"] for row in cursor.fetchall()}
            total_reminders = conn.execute("SELECT count(*) FROM reminders;").fetchone()[0]

        pending = status_counts.get("pending", 0)
        ready = status_counts.get("ready", 0)
        processing = status_counts.get("processing", 0)
        simulated = status_counts.get("simulated", 0)
        smtp_accepted = status_counts.get("sent", 0)
        failed = status_counts.get("failed", 0)
        delivery_unknown = status_counts.get("delivery_unknown", 0)

        # Invariant: attempted = simulated + sent + failed (excludes pending, ready, processing, delivery_unknown)
        attempted = simulated + smtp_accepted + failed
        success_rate = ((simulated + smtp_accepted) / attempted * 100.0) if attempted > 0 else 0.0

        status_rows = [
            ("pending", pending, "Pending", "Reminders awaiting scheduled due timestamp"),
            ("ready", ready, "Ready", "Reminders prepared and staged for dispatch"),
            ("processing", processing, "Processing", "Reminders actively claimed by transport worker"),
            ("simulated", simulated, "Simulated", "Reminders dispatched via safe dry-run simulation"),
            ("sent", smtp_accepted, "Sent (SMTP Accepted)", "Messages accepted by Gmail SMTP (remote acceptance; not confirmed delivery)"),
            ("failed", failed, "Failed", "Definitive dispatch failures recorded with error details"),
            ("delivery_unknown", delivery_unknown, "Delivery Unknown", "Ambiguous transmission outcomes quarantined from automatic retry"),
            ("total", total_reminders, "Total Reminders", "Total registered reminder records across all states"),
            ("attempted", attempted, "Attempted Dispatches", "Total dispatch attempts (simulated + smtp_accepted + failed; excludes pending, ready, processing, delivery_unknown)"),
            ("success_rate", f"{success_rate:.1f}%", "Success Rate", "Ratio of accepted/simulated outcomes to total attempts (excludes delivery_unknown)"),
        ]

        headers = ["status", "count", "display_name", "description"]

        with open(file_path, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for st, cnt, disp, desc in status_rows:
                writer.writerow([
                    sanitize_csv_value(st),
                    sanitize_csv_value(cnt),
                    sanitize_csv_value(disp),
                    sanitize_csv_value(desc),
                ])

        logger.info("Generated Reminder Status Report at %s (%d status categories)", file_path, len(status_rows))
        log_activity(
            db_path=db_path,
            event_type="report_generated",
            severity="INFO",
            status="success",
            message=f"Generated Reminder Status Report ({len(status_rows)} categories) to {file_path.name}",
            details={"report_type": "reminder_status", "record_count": len(status_rows), "path": str(file_path)},
        )

        return ReportResult(
            report_type="reminder_status",
            file_path=file_path,
            record_count=len(status_rows),
            generated_at=now_iso,
        )
    except Exception as err:
        logger.error("Failed to generate Reminder Status Report: %s", err)
        log_activity(
            db_path=db_path,
            event_type="report_generation_failed",
            severity="ERROR",
            status="failed",
            message=f"Failed to generate Reminder Status Report: {err}",
            details={"report_type": "reminder_status", "error": str(err)},
        )
        raise


def generate_reminder_details_report(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    output_dir: Optional[Union[Path, str]] = None,
) -> ReportResult:
    """Generates an operational snapshot report containing detailed records of every reminder in the system.
    
    Retained as an optional report distinct from the required Reminder Status Count Report.
    """
    out_dir = Path(output_dir) if output_dir else DEFAULT_REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = out_dir / f"reminder_details_report_{_get_timestamp_slug()}.csv"
    now_iso = datetime.now(timezone.utc).isoformat()

    query = """
        SELECT 
            r.reminder_id,
            r.contact_id,
            coalesce(c.first_name || ' ' || c.last_name, '') AS contact_name,
            coalesce(c.company, '') AS company,
            coalesce(c.email, '') AS recipient_email,
            r.reminder_type,
            r.template_key,
            r.due_at,
            r.status,
            r.reference_id,
            r.notes,
            r.created_at,
            r.updated_at
        FROM reminders r
        LEFT JOIN contacts c ON r.contact_id = c.contact_id
        ORDER BY r.due_at ASC, r.reminder_id ASC;
    """

    headers = [
        "reminder_id",
        "contact_id",
        "contact_name",
        "company",
        "recipient_email",
        "reminder_type",
        "template_key",
        "due_at",
        "status",
        "reference_id",
        "notes",
        "created_at",
        "updated_at",
    ]

    record_count = 0
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.execute(query)
            rows = cursor.fetchall()

            with open(file_path, mode="w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for row in rows:
                    writer.writerow([
                        sanitize_csv_value(row["reminder_id"]),
                        sanitize_csv_value(row["contact_id"]),
                        sanitize_csv_value(row["contact_name"]),
                        sanitize_csv_value(row["company"]),
                        sanitize_csv_value(row["recipient_email"]),
                        sanitize_csv_value(row["reminder_type"]),
                        sanitize_csv_value(row["template_key"]),
                        sanitize_csv_value(row["due_at"]),
                        sanitize_csv_value(row["status"]),
                        sanitize_csv_value(row["reference_id"]),
                        sanitize_csv_value(row["notes"]),
                        sanitize_csv_value(row["created_at"]),
                        sanitize_csv_value(row["updated_at"]),
                    ])
                    record_count += 1

        logger.info("Generated Reminder Details Report at %s (%d records)", file_path, record_count)
        log_activity(
            db_path=db_path,
            event_type="report_generated",
            severity="INFO",
            status="success",
            message=f"Generated Reminder Details Report ({record_count} records) to {file_path.name}",
            details={"report_type": "reminder_details", "record_count": record_count, "path": str(file_path)},
        )

        return ReportResult(
            report_type="reminder_details",
            file_path=file_path,
            record_count=record_count,
            generated_at=now_iso,
        )
    except Exception as err:
        logger.error("Failed to generate Reminder Details Report: %s", err)
        log_activity(
            db_path=db_path,
            event_type="report_generation_failed",
            severity="ERROR",
            status="failed",
            message=f"Failed to generate Reminder Details Report: {err}",
            details={"report_type": "reminder_details", "error": str(err)},
        )
        raise


def generate_activity_history_report(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    output_dir: Optional[Union[Path, str]] = None,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
) -> ReportResult:
    """Generates an audit report exporting persistent event history from the activity_logs table."""
    out_dir = Path(output_dir) if output_dir else DEFAULT_REPORTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = out_dir / f"activity_history_report_{_get_timestamp_slug()}.csv"
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        logs = get_activity_logs(
            db_path=db_path,
            start_date=start_date,
            end_date=end_date,
            event_type=event_type,
            severity=severity,
            status=status,
        )

        headers = [
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

        record_count = 0
        with open(file_path, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for log in logs:
                writer.writerow([
                    sanitize_csv_value(log.log_id),
                    sanitize_csv_value(log.timestamp),
                    sanitize_csv_value(log.event_type),
                    sanitize_csv_value(log.severity),
                    sanitize_csv_value(log.reminder_id or ""),
                    sanitize_csv_value(log.contact_id or ""),
                    sanitize_csv_value(log.status),
                    sanitize_csv_value(log.message),
                    sanitize_csv_value(log.details or ""),
                ])
                record_count += 1

        logger.info("Generated Activity History Report at %s (%d records)", file_path, record_count)
        log_activity(
            db_path=db_path,
            event_type="report_generated",
            severity="INFO",
            status="success",
            message=f"Generated Activity History Report ({record_count} records) to {file_path.name}",
            details={"report_type": "activity_history", "record_count": record_count, "path": str(file_path)},
        )

        return ReportResult(
            report_type="activity_history",
            file_path=file_path,
            record_count=record_count,
            generated_at=now_iso,
        )
    except Exception as err:
        logger.error("Failed to generate Activity History Report: %s", err)
        log_activity(
            db_path=db_path,
            event_type="report_generation_failed",
            severity="ERROR",
            status="failed",
            message=f"Failed to generate Activity History Report: {err}",
            details={"report_type": "activity_history", "error": str(err)},
        )
        raise
