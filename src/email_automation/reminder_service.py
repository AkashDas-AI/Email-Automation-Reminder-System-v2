"""Reminder Processing Service Module

Author: Akash Das
Responsibility: Orchestrates state transitions, identifies due reminders, invokes personalization, and prepares dispatch queues.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Union

from .database import (
    DEFAULT_DB_PATH,
    get_all_prepared_emails,
    get_contact_by_id,
    get_pending_reminders,
    log_activity,
    transition_reminder_to_ready,
)
from .models import Contact, PersonalizedEmail, Reminder, SchedulingSummary
from .personalization import (
    ContactNotFoundError,
    PersonalizationError,
    TemplateNotFoundError,
    personalize_reminder,
)

logger = logging.getLogger(__name__)


def parse_iso_utc_timestamp(timestamp_str: str) -> datetime:
    """Parses an ISO 8601 string into a timezone-aware UTC datetime object.
    
    Raises:
        ValueError: If the string is malformed or lacks timezone information.
    """
    cleaned = timestamp_str.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        raise ValueError(f"Timestamp '{timestamp_str}' is naive. All timestamps must be timezone-aware UTC.")
    
    return dt.astimezone(timezone.utc)


def run_due_reminders_once(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    template_dir: Union[Path, str] = "templates/email_templates",
    now_utc: Optional[datetime] = None,
) -> SchedulingSummary:
    """Evaluates all pending reminders and transitions due ones to 'ready' status.
    
    Args:
        db_path: Path to the SQLite database file.
        template_dir: Directory containing email template files.
        now_utc: Optional reference datetime; defaults to datetime.now(timezone.utc).
        
    Returns:
        SchedulingSummary: Summary containing execution counts, prepared IDs, and errors.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    elif now_utc.tzinfo is None:
        raise ValueError("now_utc must be a timezone-aware datetime.")
    else:
        now_utc = now_utc.astimezone(timezone.utc)

    pending_reminders = get_pending_reminders(db_path)
    examined_count = len(pending_reminders)
    due_count = 0
    prepared_ids: List[str] = []
    errors: List[str] = []

    for reminder in pending_reminders:
        # 1. Parse and validate due_at timestamp
        try:
            due_at_dt = parse_iso_utc_timestamp(reminder.due_at)
        except Exception as e:
            err_msg = f"Reminder {reminder.reminder_id}: Invalid due_at timestamp '{reminder.due_at}' ({e})"
            logger.warning(err_msg)
            errors.append(err_msg)
            continue

        # 2. Check if reminder is due
        if due_at_dt <= now_utc:
            due_count += 1
            
            # 3. Retrieve contact
            contact = get_contact_by_id(db_path, reminder.contact_id)
            if contact is None:
                err_msg = (
                    f"Reminder {reminder.reminder_id}: Referencing missing contact '{reminder.contact_id}'."
                )
                logger.error(err_msg)
                errors.append(err_msg)
                log_activity(
                    db_path=db_path,
                    event_type="reminder_preparation_failed",
                    severity="ERROR",
                    status="failed",
                    message=err_msg,
                    reminder_id=reminder.reminder_id,
                    contact_id=reminder.contact_id,
                )
                continue

            # 4. Personalize template
            try:
                prepared_email = personalize_reminder(contact, reminder, template_dir=template_dir)
            except (TemplateNotFoundError, PersonalizationError, Exception) as e:
                err_msg = f"Reminder {reminder.reminder_id}: Personalization failed ({e})"
                logger.error(err_msg)
                errors.append(err_msg)
                log_activity(
                    db_path=db_path,
                    event_type="reminder_preparation_failed",
                    severity="ERROR",
                    status="failed",
                    message=err_msg,
                    reminder_id=reminder.reminder_id,
                    contact_id=reminder.contact_id,
                )
                continue

            # 5. Atomically transition state to 'ready'
            success = transition_reminder_to_ready(db_path, reminder.reminder_id, prepared_email)
            if success:
                prepared_ids.append(reminder.reminder_id)
                logger.info("Reminder %s prepared and transitioned to READY.", reminder.reminder_id)
            else:
                logger.info("Reminder %s was claimed by another concurrent process.", reminder.reminder_id)

    # Count current remaining pending reminders
    current_pending = len(get_pending_reminders(db_path))
    failed_count = len(errors)
    prepared_count = len(prepared_ids)

    return SchedulingSummary(
        examined=examined_count,
        due=due_count,
        prepared=prepared_count,
        pending=current_pending,
        failed=failed_count,
        prepared_ids=prepared_ids,
        errors=errors,
    )


def get_prepared_queue(db_path: Union[Path, str] = DEFAULT_DB_PATH) -> List[PersonalizedEmail]:
    """Retrieves all prepared emails marked ready for dispatch in Phase 8."""
    return get_all_prepared_emails(db_path)
