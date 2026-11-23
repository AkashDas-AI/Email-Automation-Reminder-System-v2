"""Email Dispatcher & Transport Module

Author: Akash Das
Responsibility: Dispatches prepared emails via dry-run simulation or live Gmail SMTP transport with safety allowlisting.
"""

from __future__ import annotations

import logging
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import List, Optional, Union

from .config import AppConfig, ConfigurationError, load_config
from .database import (
    DEFAULT_DB_PATH,
    claim_ready_emails_for_dispatch,
    log_activity,
    update_dispatch_outcome,
)
from .models import DispatchResult, DispatchSummary, PersonalizedEmail

logger = logging.getLogger(__name__)


def build_mime_message(email: PersonalizedEmail, config: AppConfig) -> EmailMessage:
    """Builds a multipart/alternative MIME EmailMessage containing HTML and text bodies."""
    msg = EmailMessage()
    msg["Subject"] = email.subject
    
    sender_name = config.email_from_name or ""
    sender_addr = config.email_from or ""
    msg["From"] = formataddr((sender_name, sender_addr))
    msg["To"] = email.recipient_email

    # Plain text content as primary payload
    msg.set_content(email.text_body)
    # HTML alternative for clients supporting rich display
    msg.add_alternative(email.html_body, subtype="html")

    return msg


class DryRunTransport:
    """Simulates email delivery locally without network connections or SMTP credentials."""

    @staticmethod
    def send(email: PersonalizedEmail) -> DispatchResult:
        """Simulates sending a prepared email without external side effects."""
        logger.info(
            "[DRY-RUN SIMULATION] Reminder %s to %s | Subject: %s",
            email.reminder_id,
            email.recipient_email,
            email.subject,
        )
        return DispatchResult(
            reminder_id=email.reminder_id,
            recipient_email=email.recipient_email,
            status="simulated",
            error_message=None,
        )


class GmailSMTPTransport:
    """Dispatches emails over secure Gmail SMTP using STARTTLS on port 587."""

    @staticmethod
    def send(
        email: PersonalizedEmail,
        config: AppConfig,
        timeout_seconds: int = 30,
    ) -> DispatchResult:
        """Transmits email payload to Gmail SMTP server with recipient allowlisting."""
        # 1. Recipient Allowlist Verification (Critical Safety Gate)
        recipient_clean = email.recipient_email.strip().lower()
        if recipient_clean not in config.smtp_allowed_recipients:
            err_msg = (
                f"Recipient '{email.recipient_email}' is not in the live-send allowlist "
                f"(SMTP_ALLOWED_RECIPIENTS). Live delivery aborted for safety."
            )
            logger.warning("[SAFETY INTERVENTION] %s", err_msg)
            return DispatchResult(
                reminder_id=email.reminder_id,
                recipient_email=email.recipient_email,
                status="failed",
                error_message=err_msg,
            )

        # 2. Build MIME message container
        msg = build_mime_message(email, config)

        # 3. Connect and Transmit via STARTTLS
        server = None
        transmission_started = False
        try:
            context = ssl.create_default_context()
            server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=timeout_seconds)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(config.smtp_username or "", config.smtp_password or "")

            transmission_started = True
            server.send_message(msg)
            server.quit()
            server = None

            logger.info("SMTP server accepted message for %s (Reminder: %s)", email.recipient_email, email.reminder_id)
            return DispatchResult(
                reminder_id=email.reminder_id,
                recipient_email=email.recipient_email,
                status="sent",
                error_message=None,
            )

        except smtplib.SMTPAuthenticationError as e:
            err_msg = f"SMTP Authentication failed for user '{config.smtp_username}'."
            logger.error("[SMTP AUTH ERROR] %s", err_msg)
            return DispatchResult(
                reminder_id=email.reminder_id,
                recipient_email=email.recipient_email,
                status="failed",
                error_message=err_msg,
            )

        except smtplib.SMTPConnectError as e:
            err_msg = f"Definitive SMTP connection failure: {type(e).__name__} ({e})"
            logger.error("[SMTP CONNECT ERROR] %s", err_msg)
            return DispatchResult(
                reminder_id=email.reminder_id,
                recipient_email=email.recipient_email,
                status="failed",
                error_message=err_msg,
            )

        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError, smtplib.SMTPResponseException, smtplib.SMTPHeloError) as e:
            err_msg = f"Definitive SMTP transmission error: {type(e).__name__} ({e})"
            logger.error("[SMTP TRANSMISSION ERROR] %s", err_msg)
            return DispatchResult(
                reminder_id=email.reminder_id,
                recipient_email=email.recipient_email,
                status="failed",
                error_message=err_msg,
            )

        except (socket.timeout, TimeoutError, smtplib.SMTPServerDisconnected, ConnectionResetError, BrokenPipeError, OSError) as e:
            if transmission_started:
                # Ambiguous state: payload may or may not have been accepted by Gmail
                err_msg = (
                    f"Ambiguous transmission outcome: Connection dropped or timed out during delivery ({type(e).__name__}). "
                    f"Message status is 'delivery_unknown'; manual reconciliation required to prevent duplicates."
                )
                logger.critical("[AMBIGUOUS DELIVERY FAILURE] %s", err_msg)
                return DispatchResult(
                    reminder_id=email.reminder_id,
                    recipient_email=email.recipient_email,
                    status="delivery_unknown",
                    error_message=err_msg,
                )
            else:
                err_msg = f"Failed to connect to SMTP server: {type(e).__name__} ({e})"
                logger.error("[SMTP CONNECTION ERROR] %s", err_msg)
                return DispatchResult(
                    reminder_id=email.reminder_id,
                    recipient_email=email.recipient_email,
                    status="failed",
                    error_message=err_msg,
                )

        except Exception as e:
            if transmission_started:
                err_msg = (
                    f"Ambiguous transmission outcome: Unexpected error after delivery initiated ({type(e).__name__}: {e}). "
                    f"Message status is 'delivery_unknown'; manual reconciliation required to prevent duplicates."
                )
                logger.critical("[AMBIGUOUS DELIVERY FAILURE] %s", err_msg)
                return DispatchResult(
                    reminder_id=email.reminder_id,
                    recipient_email=email.recipient_email,
                    status="delivery_unknown",
                    error_message=err_msg,
                )
            else:
                err_msg = f"Unexpected error during SMTP connection: {type(e).__name__} ({e})"
                logger.error("[SMTP DISPATCH ERROR] %s", err_msg)
                return DispatchResult(
                    reminder_id=email.reminder_id,
                    recipient_email=email.recipient_email,
                    status="failed",
                    error_message=err_msg,
                )

        finally:
            if server is not None:
                try:
                    server.close()
                except Exception:
                    pass


def dispatch_ready_emails(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    config: Optional[AppConfig] = None,
    confirm_live_send: bool = False,
    limit: Optional[int] = None,
) -> DispatchSummary:
    """Coordinates the dispatch of all staged ready emails according to configured safety rules.
    
    Args:
        db_path: Path to the SQLite database file.
        config: Application configuration instance (loads default if None).
        confirm_live_send: Explicit flag required for live SMTP dispatch.
        limit: Optional maximum number of records to process.
        
    Returns:
        DispatchSummary: Structured summary of dispatch outcomes.
    """
    if config is None:
        config = load_config()

    # Live sending safety assertion
    if not config.dry_run and not confirm_live_send:
        raise ConfigurationError(
            "Live SMTP mode is configured (DRY_RUN=false), but live execution was not explicitly "
            "authorized. Pass confirm_live_send=True (or --confirm-live-send on the CLI) to proceed."
        )

    if not config.dry_run and confirm_live_send:
        if not config.smtp_username or not config.smtp_password or not config.email_from:
            raise ConfigurationError(
                "Live SMTP sending requires active credentials (SMTP_USERNAME, SMTP_PASSWORD, EMAIL_FROM)."
            )

    # Atomically claim records by updating status from 'ready' to 'processing'
    claimed_emails = claim_ready_emails_for_dispatch(db_path, limit=limit)
    examined_count = len(claimed_emails)
    claimed_count = examined_count

    if claimed_emails:
        log_activity(
            db_path=db_path,
            event_type="dispatch_batch_started",
            severity="INFO",
            status="processing",
            message=f"Starting dispatch batch of {claimed_count} ready emails (dry_run={config.dry_run}).",
            details={"claimed_count": claimed_count, "dry_run": config.dry_run},
        )

    simulated_count = 0
    smtp_accepted_count = 0
    failed_count = 0
    delivery_unknown_count = 0
    rejected_recipient_count = 0
    processed_ids: List[str] = []
    errors: List[str] = []

    for email in claimed_emails:
        if config.dry_run:
            result = DryRunTransport.send(email)
            try:
                update_dispatch_outcome(db_path, email.reminder_id, "simulated")
                simulated_count += 1
                processed_ids.append(email.reminder_id)
                log_activity(
                    db_path=db_path,
                    event_type="email_simulated",
                    severity="INFO",
                    status="simulated",
                    message=f"Dry-run simulation for reminder {email.reminder_id} to {email.recipient_email}.",
                    reminder_id=email.reminder_id,
                    contact_id=email.contact_id,
                    details={"recipient_email": email.recipient_email, "subject": email.subject},
                )
            except Exception as db_err:
                err_msg = f"Failed to record dry-run simulation in database: {db_err}"
                logger.error(err_msg)
                errors.append(f"Reminder {email.reminder_id}: {err_msg}")

        else:
            result = GmailSMTPTransport.send(email, config)
            if result.status == "sent":
                try:
                    update_dispatch_outcome(db_path, email.reminder_id, "sent")
                    smtp_accepted_count += 1
                    processed_ids.append(email.reminder_id)
                    log_activity(
                        db_path=db_path,
                        event_type="email_smtp_accepted",
                        severity="INFO",
                        status="sent",
                        message=f"SMTP server accepted message for reminder {email.reminder_id} to {email.recipient_email}.",
                        reminder_id=email.reminder_id,
                        contact_id=email.contact_id,
                        details={"recipient_email": email.recipient_email, "subject": email.subject},
                    )
                except Exception as db_err:
                    err_msg = (
                        f"CRITICAL: Message was accepted by SMTP server, but database update to 'sent' failed: {db_err}. "
                        f"Recording status as 'delivery_unknown' to prevent dangerous re-sends."
                    )
                    logger.critical("[POST-SEND DB FAILURE] %s", err_msg)
                    errors.append(f"Reminder {email.reminder_id}: {err_msg}")
                    try:
                        update_dispatch_outcome(db_path, email.reminder_id, "delivery_unknown", err_msg)
                        delivery_unknown_count += 1
                        processed_ids.append(email.reminder_id)
                        log_activity(
                            db_path=db_path,
                            event_type="email_delivery_unknown",
                            severity="CRITICAL",
                            status="delivery_unknown",
                            message=err_msg,
                            reminder_id=email.reminder_id,
                            contact_id=email.contact_id,
                            details={"error": err_msg},
                        )
                    except Exception as fallback_err:
                        logger.critical(
                            "[POST-SEND DB FATAL] Fallback update to 'delivery_unknown' also failed: %s. "
                            "Record remains in 'processing' status to prevent automated retry.",
                            fallback_err,
                        )

            elif result.status == "delivery_unknown":
                try:
                    update_dispatch_outcome(db_path, email.reminder_id, "delivery_unknown", result.error_message)
                    delivery_unknown_count += 1
                    processed_ids.append(email.reminder_id)
                    log_activity(
                        db_path=db_path,
                        event_type="email_delivery_unknown",
                        severity="CRITICAL",
                        status="delivery_unknown",
                        message=f"Ambiguous transmission outcome for reminder {email.reminder_id}: {result.error_message}",
                        reminder_id=email.reminder_id,
                        contact_id=email.contact_id,
                        details={"error": result.error_message, "recipient_email": email.recipient_email},
                    )
                except Exception as db_err:
                    logger.critical("[DB ERROR ON DELIVERY_UNKNOWN] Failed to record delivery_unknown: %s", db_err)
                errors.append(f"Reminder {email.reminder_id}: {result.error_message}")

            elif result.status == "failed":
                try:
                    update_dispatch_outcome(db_path, email.reminder_id, "failed", result.error_message)
                    failed_count += 1
                    if "is not in the live-send allowlist" in (result.error_message or ""):
                        rejected_recipient_count += 1
                    processed_ids.append(email.reminder_id)
                    log_activity(
                        db_path=db_path,
                        event_type="email_failed",
                        severity="ERROR",
                        status="failed",
                        message=f"Dispatch failed for reminder {email.reminder_id}: {result.error_message}",
                        reminder_id=email.reminder_id,
                        contact_id=email.contact_id,
                        details={"error": result.error_message, "recipient_email": email.recipient_email},
                    )
                except Exception as db_err:
                    logger.critical("[DB ERROR ON FAILED] Failed to record failed status: %s", db_err)
                errors.append(f"Reminder {email.reminder_id}: {result.error_message}")

    if claimed_count > 0:
        log_activity(
            db_path=db_path,
            event_type="dispatch_batch_completed",
            severity="INFO" if not errors else "WARNING",
            status="success" if not errors else "partial_failure",
            message=f"Dispatch batch completed: {simulated_count} simulated, {smtp_accepted_count} smtp_accepted, {failed_count} failed, {delivery_unknown_count} delivery_unknown.",
            details={
                "examined": examined_count,
                "simulated": simulated_count,
                "smtp_accepted": smtp_accepted_count,
                "failed": failed_count,
                "delivery_unknown": delivery_unknown_count,
                "errors_count": len(errors),
            },
        )

    return DispatchSummary(
        examined=examined_count,
        claimed=claimed_count,
        simulated=simulated_count,
        smtp_accepted=smtp_accepted_count,
        failed=failed_count,
        delivery_unknown=delivery_unknown_count,
        rejected_recipient=rejected_recipient_count,
        processed_ids=processed_ids,
        errors=errors,
    )
