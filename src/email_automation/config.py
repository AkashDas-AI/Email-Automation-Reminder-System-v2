"""Configuration Management Module

Author: Akash Das
Responsibility: Loads, resolves, and validates environment variables for application runtime and SMTP connectivity.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union
from dotenv import load_dotenv


class ConfigurationError(Exception):
    """Custom exception raised when system configuration is invalid or missing required values."""
    pass


@dataclass(frozen=True)
class AppConfig:
    """Immutable application configuration container."""
    dry_run: bool = True
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_allowed_recipients: Tuple[str, ...] = ()
    email_from: Optional[str] = None
    email_from_name: str = "Email Automation Reminder System"
    timezone: str = "UTC"
    log_level: str = "INFO"
    log_file: str = "logs/email_automation.log"
    reports_dir: str = "outputs/reports"

    def __repr__(self) -> str:
        """Safe representation ensuring sensitive credentials are never displayed or logged."""
        masked_pwd = "********" if self.smtp_password else None
        return (
            f"AppConfig(dry_run={self.dry_run}, smtp_host={self.smtp_host!r}, "
            f"smtp_port={self.smtp_port}, smtp_username={self.smtp_username!r}, "
            f"smtp_password={masked_pwd!r}, smtp_allowed_recipients={self.smtp_allowed_recipients!r}, "
            f"email_from={self.email_from!r}, email_from_name={self.email_from_name!r}, "
            f"timezone={self.timezone!r}, log_level={self.log_level!r}, "
            f"log_file={self.log_file!r}, reports_dir={self.reports_dir!r})"
        )


def parse_bool(value: Optional[str], default: bool = True) -> bool:
    """Parses environment strings into boolean values safely."""
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes", "t", "y")


def load_config(env_path: Optional[Union[Path, str]] = None, override_env: bool = False) -> AppConfig:
    """Loads configuration from environment variables or a specific .env file.
    
    Args:
        env_path: Optional path to a specific .env file.
        override_env: Whether to override existing environment variables.
        
    Returns:
        AppConfig: Validated application configuration instance.
        
    Raises:
        ConfigurationError: If any configuration value is invalid or required fields are missing.
    """
    if env_path:
        load_dotenv(dotenv_path=env_path, override=override_env)
    else:
        load_dotenv(override=override_env)

    # 1. Parse Delivery Mode
    dry_run = parse_bool(os.getenv("DRY_RUN"), default=True)

    # 2. Parse SMTP Host
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    if not smtp_host:
        smtp_host = "smtp.gmail.com"

    # 3. Parse and Validate Port
    port_raw = os.getenv("SMTP_PORT", "587").strip()
    try:
        smtp_port = int(port_raw)
        if smtp_port < 1 or smtp_port > 65535:
            raise ValueError()
    except ValueError:
        raise ConfigurationError(f"Invalid SMTP_PORT: '{port_raw}'. Port must be an integer between 1 and 65535.")

    # 4. Parse Credentials
    smtp_username = os.getenv("SMTP_USERNAME")
    if smtp_username is not None:
        smtp_username = smtp_username.strip() or None

    smtp_password = os.getenv("SMTP_PASSWORD")
    if smtp_password is not None:
        smtp_password = smtp_password.strip() or None

    # 5. Parse Recipient Allowlist
    allowed_raw = os.getenv("SMTP_ALLOWED_RECIPIENTS", "")
    allowed_recipients = tuple(
        e.strip().lower() for e in allowed_raw.split(",") if e.strip()
    )

    # 6. Parse Sender Details
    email_from = os.getenv("EMAIL_FROM")
    if email_from is not None:
        email_from = email_from.strip() or None

    email_from_name = os.getenv("EMAIL_FROM_NAME", "Email Automation Reminder System").strip()
    timezone = os.getenv("TIMEZONE", "UTC").strip() or "UTC"
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    log_file = os.getenv("LOG_FILE", "logs/email_automation.log").strip() or "logs/email_automation.log"
    reports_dir = os.getenv("REPORTS_DIR", "outputs/reports").strip() or "outputs/reports"

    # 7. Validate Mode-Specific Requirements
    if not dry_run:
        missing_fields = []
        if not smtp_username:
            missing_fields.append("SMTP_USERNAME")
        if not smtp_password:
            missing_fields.append("SMTP_PASSWORD")
        if not email_from:
            missing_fields.append("EMAIL_FROM")

        if missing_fields:
            raise ConfigurationError(
                f"SMTP delivery mode (DRY_RUN=false) requires active credentials. "
                f"Missing required settings: {', '.join(missing_fields)}"
            )

    return AppConfig(
        dry_run=dry_run,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        smtp_allowed_recipients=allowed_recipients,
        email_from=email_from,
        email_from_name=email_from_name,
        timezone=timezone,
        log_level=log_level,
        log_file=log_file,
        reports_dir=reports_dir,
    )
