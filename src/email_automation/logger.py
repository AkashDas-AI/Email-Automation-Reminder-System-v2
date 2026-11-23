"""Centralized Application Logging Module

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Configures consistent log formatting, file rotation/persistence in logs/,
console output, and prevents duplicate handlers.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional, Union

DEFAULT_LOG_FILE = Path("logs/email_automation.log")
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def resolve_log_level(level: Union[int, str]) -> int:
    """Converts string or int log level representation to standard logging integer constants."""
    if isinstance(level, int):
        return level
    lvl_str = str(level).strip().upper()
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
        "FATAL": logging.CRITICAL,
    }
    return level_map.get(lvl_str, logging.INFO)


def setup_logging(
    log_level: Union[int, str] = "INFO",
    log_file: Optional[Union[Path, str]] = DEFAULT_LOG_FILE,
    console: bool = True,
    logger_name: str = "email_automation",
) -> logging.Logger:
    """Configures centralized logging with consistent formatting and duplicate handler prevention.
    
    Args:
        log_level: Desired minimum log severity (INFO, WARNING, ERROR, CRITICAL, DEBUG).
        log_file: Target file path to persist application logs. Pass None to disable file logging.
        console: Whether to attach a stdout StreamHandler for CLI execution.
        logger_name: Target logger hierarchy namespace.
        
    Returns:
        logging.Logger: The configured Logger instance.
    """
    logger = logging.getLogger(logger_name)
    resolved_level = resolve_log_level(log_level)
    logger.setLevel(resolved_level)

    # Prevent duplicate handlers on re-initialization
    if logger.hasHandlers():
        logger.handlers.clear()

    # Prevent log propagation to root logger to avoid duplicate prints if root is configured
    logger.propagate = False

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    # 1. Console Stream Handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(resolved_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # 2. Persistent File Handler
    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(file_path), encoding="utf-8")
        file_handler.setLevel(resolved_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Convenience getter returning a child logger within the email_automation namespace."""
    if not name:
        return logging.getLogger("email_automation")
    if name.startswith("email_automation"):
        return logging.getLogger(name)
    return logging.getLogger(f"email_automation.{name}")
