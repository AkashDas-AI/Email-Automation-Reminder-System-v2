"""Email Personalization Engine Module

Author: Akash Das
Responsibility: Merges contact records and reminder tasks with email templates to generate personalized HTML and text messages.
"""

from __future__ import annotations

import csv
import html
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

from .models import Contact, PersonalizedEmail, Reminder


class PersonalizationError(Exception):
    """Base exception for email personalization errors."""
    pass


class TemplateNotFoundError(PersonalizationError):
    """Raised when an HTML or text template cannot be found for a template_key."""
    pass


class ContactNotFoundError(PersonalizationError):
    """Raised when a reminder references a non-existent contact_id."""
    pass


class PlaceholderValidationError(PersonalizationError):
    """Raised when a template contains unknown or unresolvable placeholders."""
    pass


# Supported template keys
SUPPORTED_TEMPLATE_KEYS: Set[str] = {
    "meeting",
    "payment",
    "deadline",
    "follow_up",
    "general",
}

# Standardized subject templates
SUBJECT_TEMPLATES: Dict[str, str] = {
    "meeting": "Meeting Reminder: {notes} [Ref: #{reference_id}]",
    "payment": "Payment Notice: Upcoming payment for invoice #{reference_id}",
    "deadline": "Deadline Reminder: Action required for {notes} [Ref: #{reference_id}]",
    "follow_up": "Follow-Up Request: Status update regarding {notes} [Ref: #{reference_id}]",
    "general": "Notice: {reminder_type} update for {company} - Ref: #{reference_id}",
}

# Globally documented allowed placeholders
ALLOWED_PLACEHOLDERS: Set[str] = {
    "first_name",
    "last_name",
    "full_name",
    "email",
    "department",
    "company",
    "reminder_type",
    "due_at",
    "reference_id",
    "notes",
}

PLACEHOLDER_REGEX = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def load_contacts_dict(csv_path: Union[Path, str]) -> Dict[str, Contact]:
    """Loads contacts from a CSV file into a dictionary keyed by contact_id."""
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Contacts CSV not found: {path}")

    contacts: Dict[str, Contact] = {}
    with open(path, mode="r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            contact = Contact(
                contact_id=row["contact_id"].strip(),
                first_name=row["first_name"].strip(),
                last_name=row["last_name"].strip(),
                email=row["email"].strip(),
                department=row["department"].strip(),
                company=row["company"].strip(),
            )
            contacts[contact.contact_id] = contact
    return contacts


def load_reminders_list(csv_path: Union[Path, str]) -> List[Reminder]:
    """Loads reminders from a CSV file into a list of Reminder entities."""
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Reminders CSV not found: {path}")

    reminders: List[Reminder] = []
    with open(path, mode="r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            reminder = Reminder(
                reminder_id=row["reminder_id"].strip(),
                contact_id=row["contact_id"].strip(),
                reminder_type=row["reminder_type"].strip(),
                template_key=row["template_key"].strip(),
                due_at=row["due_at"].strip(),
                status=row["status"].strip(),
                reference_id=row.get("reference_id", "").strip(),
                notes=row["notes"].strip(),
            )
            reminders.append(reminder)
    return reminders


def resolve_template_paths(template_key: str, template_dir: Union[Path, str]) -> tuple[Path, Path]:
    """Resolves and validates the existence of HTML and TXT template files for a template_key."""
    if template_key not in SUPPORTED_TEMPLATE_KEYS:
        raise TemplateNotFoundError(
            f"Unsupported template key: '{template_key}'. Must be one of {sorted(SUPPORTED_TEMPLATE_KEYS)}."
        )

    base_dir = Path(template_dir)
    html_path = base_dir / f"{template_key}_reminder.html"
    txt_path = base_dir / f"{template_key}_reminder.txt"

    if not html_path.is_file():
        raise TemplateNotFoundError(f"HTML template file not found: {html_path}")
    if not txt_path.is_file():
        raise TemplateNotFoundError(f"Plain-text template file not found: {txt_path}")

    return html_path, txt_path


def build_personalization_context(contact: Contact, reminder: Reminder) -> Dict[str, str]:
    """Constructs the raw key-value mapping for placeholder substitution."""
    return {
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "full_name": contact.full_name,
        "email": contact.email,
        "department": contact.department,
        "company": contact.company,
        "reminder_type": reminder.reminder_type,
        "due_at": reminder.due_at,
        "reference_id": reminder.reference_id,
        "notes": reminder.notes,
    }


def validate_template_placeholders(template_content: str, available_context: Dict[str, str], template_name: str) -> None:
    """Validates placeholders against individual template requirements.
    
    A template only validates the placeholders it actually uses. Unknown placeholders
    or placeholders missing from the context will trigger an error.
    """
    found_placeholders = set(PLACEHOLDER_REGEX.findall(template_content))
    
    # 1. Reject unknown placeholders
    unknown_placeholders = found_placeholders - ALLOWED_PLACEHOLDERS
    if unknown_placeholders:
        raise PlaceholderValidationError(
            f"Template '{template_name}' contains unknown placeholder(s): {sorted(unknown_placeholders)}. "
            f"Allowed placeholders are: {sorted(ALLOWED_PLACEHOLDERS)}"
        )

    # 2. Check for missing required values for the placeholders this template requires
    missing_keys = [key for key in found_placeholders if key not in available_context or available_context[key] is None]
    if missing_keys:
        raise PlaceholderValidationError(
            f"Template '{template_name}' requires placeholder(s) {sorted(missing_keys)} missing from context."
        )


def render_text_template(template_str: str, context: Dict[str, str], template_name: str = "text") -> str:
    """Substitutes placeholders into plain-text without HTML escaping."""
    validate_template_placeholders(template_str, context, template_name)
    
    rendered = template_str
    for key, value in context.items():
        rendered = rendered.replace(f"{{{key}}}", str(value) if value is not None else "")
    
    # Verify no unresolved placeholders remain
    remaining = PLACEHOLDER_REGEX.findall(rendered)
    if remaining:
        raise PlaceholderValidationError(f"Unresolved placeholder(s) in {template_name}: {remaining}")
    return rendered


def render_html_template(template_str: str, context: Dict[str, str], template_name: str = "html") -> str:
    """Substitutes placeholders into HTML with automatic entity escaping to prevent HTML injection."""
    validate_template_placeholders(template_str, context, template_name)
    
    # HTML-escape all user-provided context values
    escaped_context = {
        key: html.escape(str(value), quote=True) if value is not None else ""
        for key, value in context.items()
    }
    
    rendered = template_str
    for key, value in escaped_context.items():
        rendered = rendered.replace(f"{{{key}}}", value)
    
    remaining = PLACEHOLDER_REGEX.findall(rendered)
    if remaining:
        raise PlaceholderValidationError(f"Unresolved placeholder(s) in {template_name}: {remaining}")
    return rendered


def generate_subject(template_key: str, context: Dict[str, str]) -> str:
    """Generates the standardized subject line for a given template_key."""
    if template_key not in SUBJECT_TEMPLATES:
        raise TemplateNotFoundError(f"No subject template configured for key '{template_key}'.")
    
    raw_subject = SUBJECT_TEMPLATES[template_key]
    validate_template_placeholders(raw_subject, context, f"subject_{template_key}")
    
    # Subjects do not need HTML escaping, but must resolve all placeholders
    subject = raw_subject
    for key, value in context.items():
        subject = subject.replace(f"{{{key}}}", str(value) if value is not None else "")
    
    remaining = PLACEHOLDER_REGEX.findall(subject)
    if remaining:
        raise PlaceholderValidationError(f"Unresolved placeholder(s) in subject: {remaining}")
    return subject


def personalize_reminder(
    contact: Contact,
    reminder: Reminder,
    template_dir: Union[Path, str] = "templates/email_templates",
) -> PersonalizedEmail:
    """Renders a single personalized email combining contact and reminder data.
    
    Args:
        contact: Recipient Contact entity.
        reminder: Target Reminder entity.
        template_dir: Directory containing HTML and TXT email template files.
        
    Returns:
        PersonalizedEmail: Structured container with subject, HTML body, and text body.
    """
    if reminder.contact_id != contact.contact_id:
        raise PersonalizationError(
            f"Mismatched Contact/Reminder pairing: Reminder {reminder.reminder_id} "
            f"belongs to contact {reminder.contact_id}, but received {contact.contact_id}."
        )

    html_path, txt_path = resolve_template_paths(reminder.template_key, template_dir)
    
    html_raw = html_path.read_text(encoding="utf-8")
    txt_raw = txt_path.read_text(encoding="utf-8")
    
    context = build_personalization_context(contact, reminder)
    
    subject = generate_subject(reminder.template_key, context)
    html_body = render_html_template(html_raw, context, template_name=html_path.name)
    text_body = render_text_template(txt_raw, context, template_name=txt_path.name)
    
    return PersonalizedEmail(
        reminder_id=reminder.reminder_id,
        contact_id=contact.contact_id,
        recipient_email=contact.email,
        recipient_name=contact.full_name,
        template_key=reminder.template_key,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        due_at=reminder.due_at,
        reference_id=reminder.reference_id,
    )


def personalize_dataset(
    contacts: Dict[str, Contact],
    reminders: List[Reminder],
    template_dir: Union[Path, str] = "templates/email_templates",
) -> List[PersonalizedEmail]:
    """Processes a batch of reminders, matching each to its contact and rendering personalized emails.
    
    Args:
        contacts: Dictionary mapping contact_id to Contact entities.
        reminders: List of Reminder entities.
        template_dir: Directory containing email template files.
        
    Returns:
        List[PersonalizedEmail]: Structured list of all rendered emails.
    """
    results: List[PersonalizedEmail] = []
    for reminder in reminders:
        if reminder.contact_id not in contacts:
            raise ContactNotFoundError(
                f"Reminder '{reminder.reminder_id}' references unknown contact_id '{reminder.contact_id}'."
            )
        contact = contacts[reminder.contact_id]
        personalized = personalize_reminder(contact, reminder, template_dir=template_dir)
        results.append(personalized)
    return results
