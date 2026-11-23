"""Command Line Interface (CLI) Entry Point

Project: Email Automation & Reminder System
Author: Akash Das
Role: Dispatches CLI operations, database initialization, and background scheduling services.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure src/ is on sys.path for direct CLI execution
sys.path.insert(0, str(Path(__file__).parent / "src"))

from email_automation.database import (
    DEFAULT_DB_PATH,
    init_db,
    migrate_db,
    import_or_sync_csv,
    get_all_prepared_emails,
    get_stale_processing_reminders,
    reconcile_stale_processing_records,
    get_activity_logs,
    log_activity,
)
from email_automation.logger import setup_logging
from email_automation.mailer import dispatch_ready_emails
from email_automation.reminder_service import run_due_reminders_once
from email_automation.report_generator import (
    generate_activity_history_report,
    generate_email_activity_report,
    generate_reminder_details_report,
    generate_reminder_status_report,
)
from email_automation.scheduler import start_continuous_scheduler


def build_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        description="Email Automation & Reminder System - Management CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help="Path to the SQLite database file.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: init-db
    subparsers.add_parser("init-db", help="Initialize SQLite tables and indexes.")

    # Command: migrate-db
    subparsers.add_parser("migrate-db", help="Safely upgrade database schema to current version.")

    # Command: sync-data
    sync_parser = subparsers.add_parser("sync-data", help="Synchronize sample CSV datasets into SQLite.")
    sync_parser.add_argument(
        "--contacts",
        default="data/sample/contacts.csv",
        help="Path to contacts CSV.",
    )
    sync_parser.add_argument(
        "--reminders",
        default="data/sample/reminders.csv",
        help="Path to reminders CSV.",
    )

    # Command: process-due
    proc_parser = subparsers.add_parser("process-due", help="Evaluate and prepare due reminders once.")
    proc_parser.add_argument(
        "--templates",
        default="templates/email_templates",
        help="Path to templates directory.",
    )

    # Command: list-prepared
    subparsers.add_parser("list-prepared", help="List all prepared emails ready for dispatch.")

    # Command: list-stale
    subparsers.add_parser("list-stale", help="List any reminders stranded in 'processing' status.")

    # Command: reconcile-stale
    rec_parser = subparsers.add_parser(
        "reconcile-stale",
        help="Safely reconcile reminders stranded in 'processing' status after an unexpected shutdown.",
    )
    rec_parser.add_argument(
        "--target-status",
        choices=["delivery_unknown", "failed"],
        default="delivery_unknown",
        help="Conservative target status to assign to stranded records (default: delivery_unknown).",
    )
    rec_parser.add_argument(
        "--reason",
        default="Interrupted dispatch recovery: reconciled to prevent duplicate sending.",
        help="Audit explanation recorded in dispatch_error.",
    )

    # Command: send-ready
    send_parser = subparsers.add_parser("send-ready", help="Dispatch prepared emails via dry-run simulation or live SMTP.")
    send_parser.add_argument(
        "--confirm-live-send",
        action="store_true",
        default=False,
        help="Explicit confirmation required to allow live SMTP sending when DRY_RUN=false.",
    )
    send_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of ready emails to dispatch.",
    )

    # Command: start-scheduler
    sched_parser = subparsers.add_parser("start-scheduler", help="Run the continuous background reminder scheduler.")
    sched_parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Check interval in seconds.",
    )

    # Command: show-activity
    act_parser = subparsers.add_parser("show-activity", help="Show recent system audit activity history records.")
    act_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of activity events to display.",
    )
    act_parser.add_argument(
        "--event-type",
        default=None,
        help="Filter by specific event type.",
    )
    act_parser.add_argument(
        "--severity",
        default=None,
        help="Filter by severity level (INFO, WARNING, ERROR, CRITICAL).",
    )

    # Command: generate-report
    rep_parser = subparsers.add_parser(
        "generate-report",
        help="Generate CSV reports capturing email activity, reminder status, or history.",
    )
    rep_parser.add_argument(
        "--type",
        required=True,
        choices=["email-activity", "reminder-status", "reminder-details", "activity-history", "all"],
        help="Report category to produce (or 'all' for all report categories).",
    )
    rep_parser.add_argument(
        "--output-dir",
        default="outputs/reports",
        help="Target output directory for the CSV.",
    )
    rep_parser.add_argument(
        "--start-date",
        default=None,
        help="Start date filter (YYYY-MM-DD or ISO timestamp).",
    )
    rep_parser.add_argument(
        "--end-date",
        default=None,
        help="End date filter (YYYY-MM-DD or ISO timestamp).",
    )

    return parser


def _run_command(args: argparse.Namespace, db_path: Path) -> None:
    """Executes the dispatched CLI subcommand."""
    if args.command == "init-db":
        init_db(db_path)
        print(f"Database initialized successfully at: {db_path}")

    elif args.command == "migrate-db":
        applied = migrate_db(db_path)
        if applied:
            print(f"Database schema migration applied successfully at: {db_path}")
        else:
            print(f"Database schema is already up to date at: {db_path}")

    elif args.command == "sync-data":
        c_count, r_count = import_or_sync_csv(
            db_path=db_path,
            contacts_csv=args.contacts,
            reminders_csv=args.reminders,
        )
        print(f"Data sync complete: {c_count} contacts, {r_count} reminders synchronized.")

    elif args.command == "process-due":
        summary = run_due_reminders_once(db_path=db_path, template_dir=args.templates)
        print("Reminder Processing Summary:")
        print(f"  Examined: {summary.examined}")
        print(f"  Due:      {summary.due}")
        print(f"  Prepared: {summary.prepared} -> {summary.prepared_ids}")
        print(f"  Pending:  {summary.pending}")
        print(f"  Failed:   {summary.failed}")
        if summary.errors:
            print("  Errors:")
            for err in summary.errors:
                print(f"    - {err}")

    elif args.command == "list-prepared":
        prepared = get_all_prepared_emails(db_path)
        print(f"Prepared Emails in Queue ({len(prepared)}):")
        for p in prepared:
            print(f"  [{p.reminder_id}] To: {p.recipient_email} | Subject: {p.subject}")

    elif args.command == "list-stale":
        stale = get_stale_processing_reminders(db_path)
        print(f"Stranded 'processing' Reminders ({len(stale)}):")
        for r in stale:
            print(f"  [{r.reminder_id}] Type: {r.reminder_type} | Due: {r.due_at} | Status: {r.status}")

    elif args.command == "reconcile-stale":
        count = reconcile_stale_processing_records(
            db_path=db_path,
            target_status=args.target_status,
            reason=args.reason,
        )
        print(f"Reconciled {count} stranded 'processing' records to status '{args.target_status}'.")

    elif args.command == "show-activity":
        logs = get_activity_logs(
            db_path=db_path,
            event_type=args.event_type,
            severity=args.severity,
            limit=args.limit,
        )
        print(f"System Activity History ({len(logs)} records):")
        for log in logs:
            rem_tag = f" [Rem: {log.reminder_id}]" if log.reminder_id else ""
            print(f"  {log.timestamp} | {log.severity:<7} | {log.event_type:<25} | {log.status:<10} | {log.message}{rem_tag}")

    elif args.command == "generate-report":
        try:
            reports_to_run = []
            if args.type == "email-activity":
                reports_to_run.append(("email-activity", lambda: generate_email_activity_report(
                    db_path=db_path,
                    output_dir=args.output_dir,
                    start_date=args.start_date,
                    end_date=args.end_date,
                )))
            elif args.type == "reminder-status":
                reports_to_run.append(("reminder-status", lambda: generate_reminder_status_report(
                    db_path=db_path,
                    output_dir=args.output_dir,
                )))
            elif args.type == "reminder-details":
                reports_to_run.append(("reminder-details", lambda: generate_reminder_details_report(
                    db_path=db_path,
                    output_dir=args.output_dir,
                )))
            elif args.type == "activity-history":
                reports_to_run.append(("activity-history", lambda: generate_activity_history_report(
                    db_path=db_path,
                    output_dir=args.output_dir,
                    start_date=args.start_date,
                    end_date=args.end_date,
                )))
            elif args.type == "all":
                reports_to_run.append(("email-activity", lambda: generate_email_activity_report(
                    db_path=db_path,
                    output_dir=args.output_dir,
                    start_date=args.start_date,
                    end_date=args.end_date,
                )))
                reports_to_run.append(("reminder-status", lambda: generate_reminder_status_report(
                    db_path=db_path,
                    output_dir=args.output_dir,
                )))
                reports_to_run.append(("reminder-details", lambda: generate_reminder_details_report(
                    db_path=db_path,
                    output_dir=args.output_dir,
                )))
                reports_to_run.append(("activity-history", lambda: generate_activity_history_report(
                    db_path=db_path,
                    output_dir=args.output_dir,
                    start_date=args.start_date,
                    end_date=args.end_date,
                )))
            else:
                print(f"Unknown report type: {args.type}", file=sys.stderr)
                sys.exit(1)

            print("Report Generation Summary:")
            for name, gen_fn in reports_to_run:
                res = gen_fn()
                print(f"  [{res.report_type}] -> {res.file_path} ({res.record_count} records)")
        except Exception as e:
            print(f"Report Generation Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "send-ready":
        try:
            summary = dispatch_ready_emails(
                db_path=db_path,
                confirm_live_send=args.confirm_live_send,
                limit=args.limit,
            )
            print("Email Dispatch Summary:")
            print(f"  Examined:           {summary.examined}")
            print(f"  Claimed:            {summary.claimed}")
            print(f"  Simulated:          {summary.simulated}")
            print(f"  SMTP Accepted:      {summary.smtp_accepted}")
            print(f"  Failed:             {summary.failed}")
            print(f"  Delivery Unknown:   {summary.delivery_unknown}")
            print(f"  Rejected Recipient: {summary.rejected_recipient}")
            print(f"  Processed IDs:      {summary.processed_ids}")
            if summary.errors:
                print("  Errors:")
                for err in summary.errors:
                    print(f"    - {err}")
        except Exception as e:
            print(f"Dispatch Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "start-scheduler":
        print(f"Starting continuous scheduler (interval: {args.interval}s, db: {db_path}). Press Ctrl+C to stop.")
        try:
            start_continuous_scheduler(db_path=db_path, interval_seconds=args.interval)
        except KeyboardInterrupt:
            print("\nScheduler terminated by user.")


def main() -> None:
    """Main CLI execution handler."""
    setup_logging(console=False)
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    db_path = Path(args.db_path)

    log_activity(
        db_path=db_path,
        event_type="app_startup",
        severity="INFO",
        status="success",
        message=f"CLI command '{args.command}' initiated.",
        details={"command": args.command, "args": sys.argv[1:]},
    )

    try:
        _run_command(args, db_path)
        log_activity(
            db_path=db_path,
            event_type="app_shutdown",
            severity="INFO",
            status="success",
            message=f"CLI command '{args.command}' completed successfully.",
            details={"command": args.command},
        )
    except Exception as err:
        log_activity(
            db_path=db_path,
            event_type="app_shutdown",
            severity="ERROR",
            status="failed",
            message=f"CLI command '{args.command}' failed: {err}",
            details={"command": args.command, "error": str(err)},
        )
        raise


if __name__ == "__main__":
    main()
