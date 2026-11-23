"""SMTP Configuration & Transport Preparation Module

Author: Akash Das
Responsibility: Encapsulates SMTP protocol definitions, TLS configuration, and connection readiness checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple
from .config import AppConfig


@dataclass(frozen=True)
class SMTPConnectionDetails:
    """Sanitized connection parameters suitable for logging and transport setup."""
    host: str
    port: int
    use_starttls: bool
    username: str


def get_smtp_connection_details(config: AppConfig) -> SMTPConnectionDetails:
    """Extracts non-sensitive connection parameters from application configuration."""
    return SMTPConnectionDetails(
        host=config.smtp_host,
        port=config.smtp_port,
        use_starttls=(config.smtp_port == 587),
        username=config.smtp_username or "",
    )


def validate_smtp_readiness(config: AppConfig) -> Tuple[bool, str]:
    """Checks whether the configuration is structurally ready for SMTP operations.
    
    Note:
        This performs local configuration validation only. No network connections
        or remote Gmail authentications are executed.
    """
    if config.dry_run:
        return True, "System is operating in DRY_RUN mode. Outgoing emails are simulated locally."

    if not config.smtp_username or not config.smtp_password:
        return False, "SMTP configuration incomplete: Missing SMTP_USERNAME or SMTP_PASSWORD."

    if not config.email_from:
        return False, "SMTP configuration incomplete: Missing EMAIL_FROM address."

    return (
        True,
        f"SMTP configuration valid for STARTTLS transport via {config.smtp_host}:{config.smtp_port} "
        f"as {config.smtp_username}."
    )
