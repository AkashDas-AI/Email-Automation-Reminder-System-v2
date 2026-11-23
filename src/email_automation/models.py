"""Data Models & Entities Module

Author: Akash Das
Responsibility: Defines data structures, schemas, and typed representations for contacts, reminders, and delivery logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class Contact:
    """Represents a recipient contact entity."""
    contact_id: str
    first_name: str
    last_name: str
    email: str
    department: str
    company: str

    @property
    def full_name(self) -> str:
        """Returns the formatted full name of the contact."""
        return f"{self.first_name} {self.last_name}".strip()


@dataclass(frozen=True)
class Reminder:
    """Represents a scheduled reminder task entity."""
    reminder_id: str
    contact_id: str
    reminder_type: str
    template_key: str
    due_at: str
    status: str
    reference_id: str
    notes: str


@dataclass(frozen=True)
class PersonalizedEmail:
    """Structured container holding personalized email content ready for dispatch."""
    reminder_id: str
    contact_id: str
    recipient_email: str
    recipient_name: str
    template_key: str
    subject: str
    html_body: str
    text_body: str
    due_at: str
    reference_id: str


@dataclass(frozen=True)
class SchedulingSummary:
    """Structured summary returned by a one-time scheduling check run."""
    examined: int
    due: int
    prepared: int
    pending: int
    failed: int
    prepared_ids: List[str]
    errors: List[str]


@dataclass(frozen=True)
class DispatchResult:
    """Outcome of attempting to dispatch a single prepared email."""
    reminder_id: str
    recipient_email: str
    status: str  # 'simulated' | 'sent' | 'failed' | 'delivery_unknown'
    error_message: Optional[str] = None


@dataclass(frozen=True)
class DispatchSummary:
    """Structured summary returned by an email dispatch batch run."""
    examined: int
    claimed: int
    simulated: int
    smtp_accepted: int
    failed: int
    delivery_unknown: int
    rejected_recipient: int
    processed_ids: List[str]
    errors: List[str]


@dataclass(frozen=True)
class ActivityLog:
    """Represents an audit event record in the persistent activity history."""
    log_id: int
    timestamp: str
    event_type: str
    severity: str
    status: str
    message: str
    reminder_id: Optional[str] = None
    contact_id: Optional[str] = None
    details: Optional[str] = None
    message: str
    reminder_id: Optional[str] = None
    contact_id: Optional[str] = None
    details: Optional[str] = None


@dataclass(frozen=True)
class ReportResult:
    """Structured summary returned by report generator operations."""
    report_type: str
    file_path: Path
    record_count: int
    generated_at: str
