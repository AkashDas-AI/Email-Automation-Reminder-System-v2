"""Scheduler Service Module

Author: Akash Das
Responsibility: Manages recurring and time-based reminder triggers independently of UI or dashboard lifecycle.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from threading import Event
from typing import Optional, Union

import schedule

from .database import DEFAULT_DB_PATH, log_activity
from .models import SchedulingSummary
from .reminder_service import run_due_reminders_once

logger = logging.getLogger(__name__)


class ContinuousScheduler:
    """Manages periodic execution of due reminder evaluations."""

    def __init__(
        self,
        db_path: Union[Path, str] = DEFAULT_DB_PATH,
        template_dir: Union[Path, str] = "templates/email_templates",
        interval_seconds: int = 60,
    ) -> None:
        self.db_path = db_path
        self.template_dir = template_dir
        self.interval_seconds = interval_seconds
        self._scheduler = schedule.Scheduler()
        self._stop_event = Event()
        self.total_runs = 0

    def trigger_check(self) -> SchedulingSummary:
        """Executes a single check cycle."""
        self.total_runs += 1
        logger.info("Executing reminder check cycle #%d...", self.total_runs)
        summary = run_due_reminders_once(self.db_path, template_dir=self.template_dir)
        logger.info(
            "Cycle #%d completed: Examined=%d, Due=%d, Prepared=%d, Pending=%d, Failed=%d",
            self.total_runs,
            summary.examined,
            summary.due,
            summary.prepared,
            summary.pending,
            summary.failed,
        )
        log_activity(
            db_path=self.db_path,
            event_type="scheduler_cycle",
            severity="INFO",
            status="success",
            message=f"Scheduler cycle #{self.total_runs} completed: {summary.prepared} prepared, {summary.failed} failed.",
            details={
                "cycle": self.total_runs,
                "examined": summary.examined,
                "due": summary.due,
                "prepared": summary.prepared,
                "pending": summary.pending,
                "failed": summary.failed,
            },
        )
        return summary

    def start(
        self,
        run_once_immediately: bool = True,
        max_runs: Optional[int] = None,
        stop_event: Optional[Event] = None,
    ) -> None:
        """Starts the continuous scheduler loop.
        
        Args:
            run_once_immediately: Whether to execute a check immediately before entering the timer loop.
            max_runs: Optional integer to exit the loop after N cycles (useful for testing).
            stop_event: Optional threading.Event to signal loop termination.
        """
        logger.info("Starting continuous reminder scheduler (interval: %d seconds)...", self.interval_seconds)
        log_activity(
            db_path=self.db_path,
            event_type="scheduler_started",
            severity="INFO",
            status="success",
            message=f"Continuous reminder scheduler started (interval: {self.interval_seconds}s).",
            details={"interval_seconds": self.interval_seconds},
        )
        self._scheduler.clear()
        self._scheduler.every(self.interval_seconds).seconds.do(self.trigger_check)

        if run_once_immediately:
            self.trigger_check()
            if max_runs is not None and self.total_runs >= max_runs:
                return

        effective_stop = stop_event or self._stop_event
        while not effective_stop.is_set():
            self._scheduler.run_pending()
            if max_runs is not None and self.total_runs >= max_runs:
                break
            time.sleep(1)

        logger.info("Continuous scheduler stopped.")
        log_activity(
            db_path=self.db_path,
            event_type="scheduler_stopped",
            severity="INFO",
            status="success",
            message="Continuous reminder scheduler stopped.",
            details={"total_runs": self.total_runs},
        )

    def stop(self) -> None:
        """Signals the scheduler loop to stop."""
        self._stop_event.set()


def start_continuous_scheduler(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    template_dir: Union[Path, str] = "templates/email_templates",
    interval_seconds: int = 60,
    run_once_immediately: bool = True,
    max_runs: Optional[int] = None,
    stop_event: Optional[Event] = None,
) -> ContinuousScheduler:
    """Convenience helper to initialize and launch the continuous scheduler."""
    scheduler = ContinuousScheduler(
        db_path=db_path,
        template_dir=template_dir,
        interval_seconds=interval_seconds,
    )
    scheduler.start(
        run_once_immediately=run_once_immediately,
        max_runs=max_runs,
        stop_event=stop_event,
    )
    return scheduler
