"""Automated Tests for Email Personalization Engine

Author: Akash Das
Covers: Contact-to-reminder matching, template resolution, placeholder validation,
subject generation, HTML escaping, CSV immutability, and error handling.
"""

import hashlib
from pathlib import Path
import pytest

from email_automation.models import Contact, Reminder, PersonalizedEmail
from email_automation.personalization import (
    load_contacts_dict,
    load_reminders_list,
    personalize_reminder,
    personalize_dataset,
    resolve_template_paths,
    generate_subject,
    render_html_template,
    render_text_template,
    PersonalizationError,
    TemplateNotFoundError,
    ContactNotFoundError,
    PlaceholderValidationError,
    SUPPORTED_TEMPLATE_KEYS,
)


@pytest.fixture
def sample_contact() -> Contact:
    return Contact(
        contact_id="CON001",
        first_name="Aarav",
        last_name="Sharma",
        email="aarav.sharma@example.com",
        department="IT",
        company="Apex Innovations",
    )


@pytest.fixture
def sample_reminder() -> Reminder:
    return Reminder(
        reminder_id="REM001",
        contact_id="CON001",
        reminder_type="Task Deadline",
        template_key="deadline",
        due_at="2027-01-10T10:00:00Z",
        status="pending",
        reference_id="TSK-1001",
        notes="Submit Q1 cloud infrastructure upgrade plan",
    )


# 1. Valid meeting reminder matches correct contact
def test_valid_meeting_reminder_matches_correct_contact(sample_contact):
    meeting_rem = Reminder(
        reminder_id="REM002",
        contact_id="CON001",
        reminder_type="Meeting",
        template_key="meeting",
        due_at="2027-01-11T14:30:00Z",
        status="pending",
        reference_id="MTG-2001",
        notes="Q1 Strategic Architecture Sync",
    )
    result = personalize_reminder(sample_contact, meeting_rem)
    assert isinstance(result, PersonalizedEmail)
    assert result.reminder_id == "REM002"
    assert result.contact_id == "CON001"
    assert result.recipient_email == "aarav.sharma@example.com"
    assert result.recipient_name == "Aarav Sharma"
    assert "Meeting Reminder: Q1 Strategic Architecture Sync [Ref: #MTG-2001]" in result.subject
    assert "Aarav" in result.html_body
    assert "MTG-2001" in result.text_body


# 2. Every supported template key selects correct HTML and text files
@pytest.mark.parametrize("key", sorted(SUPPORTED_TEMPLATE_KEYS))
def test_every_supported_template_key_resolves(key):
    html_path, txt_path = resolve_template_paths(key, "templates/email_templates")
    assert html_path.is_file()
    assert txt_path.is_file()
    assert html_path.name == f"{key}_reminder.html"
    assert txt_path.name == f"{key}_reminder.txt"


# 3. Subject generation works for all 5 template categories
@pytest.mark.parametrize(
    "key,expected_snippet",
    [
        ("meeting", "Meeting Reminder: Sync session [Ref: #REF-100]"),
        ("payment", "Payment Notice: Upcoming payment for invoice #REF-100"),
        ("deadline", "Deadline Reminder: Action required for Sync session [Ref: #REF-100]"),
        ("follow_up", "Follow-Up Request: Status update regarding Sync session [Ref: #REF-100]"),
        ("general", "Notice: Task update for Apex Innovations - Ref: #REF-100"),
    ],
)
def test_subject_generation_all_categories(key, expected_snippet):
    ctx = {
        "notes": "Sync session",
        "reference_id": "REF-100",
        "reminder_type": "Task",
        "company": "Apex Innovations",
    }
    subj = generate_subject(key, ctx)
    assert subj == expected_snippet


# 4. All documented placeholders populated correctly where required
def test_all_placeholders_populated(sample_contact, sample_reminder):
    result = personalize_reminder(sample_contact, sample_reminder)
    assert "Aarav" in result.html_body
    assert "Sharma" in result.html_body or "Aarav Sharma" in result.html_body
    assert "aarav.sharma@example.com" in result.html_body
    assert "IT" in result.html_body
    assert "Apex Innovations" in result.html_body
    assert "2027-01-10T10:00:00Z" in result.html_body
    assert "TSK-1001" in result.html_body
    assert "Submit Q1 cloud infrastructure upgrade plan" in result.html_body


# 5. Template-specific required placeholder validation works
def test_template_specific_required_placeholder_validation():
    # Template only requiring first_name and notes
    tpl = "Hello {first_name}, task is {notes}."
    context = {"first_name": "Aarav", "notes": "Write docs"}
    rendered = render_text_template(tpl, context, "custom_tpl")
    assert rendered == "Hello Aarav, task is Write docs."


# 6. Unknown or unresolved placeholders detected
def test_unknown_placeholder_rejected():
    tpl = "Hello {unknown_field_123}!"
    with pytest.raises(PlaceholderValidationError, match="contains unknown placeholder"):
        render_text_template(tpl, {"unknown_field_123": "val"}, "bad_tpl")


def test_unresolved_placeholder_detected():
    tpl = "Hello {first_name} and {notes}!"
    # notes missing from context
    with pytest.raises(PlaceholderValidationError, match="missing from context"):
        render_text_template(tpl, {"first_name": "Aarav"}, "missing_notes_tpl")


# 7. Missing contact references handled safely
def test_missing_contact_reference_handled_safely():
    contacts = {
        "CON001": Contact("CON001", "Aarav", "Sharma", "a@example.com", "IT", "Apex")
    }
    reminders = [
        Reminder("REM999", "CON999", "Task", "deadline", "2027-01-01T00:00:00Z", "pending", "REF", "Notes")
    ]
    with pytest.raises(ContactNotFoundError, match="unknown contact_id 'CON999'"):
        personalize_dataset(contacts, reminders)


# 8. Empty optional fields handled appropriately
def test_empty_optional_reference_id_handled():
    contact = Contact("CON001", "Aarav", "", "a@example.com", "IT", "Apex")
    reminder = Reminder("REM001", "CON001", "Task", "deadline", "2027-01-01T00:00:00Z", "pending", "", "Notes")
    result = personalize_reminder(contact, reminder)
    assert result.reference_id == ""
    assert result.recipient_name == "Aarav"


# 9. HTML-sensitive contact values are escaped
def test_html_sensitive_values_escaped():
    contact = Contact(
        contact_id="CON001",
        first_name="<script>alert('xss')</script>",
        last_name="O'Connor & Sons",
        email="test@example.com",
        department="IT & Security",
        company="Bold \"Innovations\"",
    )
    reminder = Reminder(
        reminder_id="REM001",
        contact_id="CON001",
        reminder_type="Task Deadline",
        template_key="deadline",
        due_at="2027-01-10T10:00:00Z",
        status="pending",
        reference_id="TSK-1001",
        notes="Fix <critical> bug & review",
    )
    result = personalize_reminder(contact, reminder)
    # HTML body must have escaped entities
    assert "<script>" not in result.html_body
    assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in result.html_body
    assert "Fix &lt;critical&gt; bug &amp; review" in result.html_body
    assert "Bold &quot;Innovations&quot;" in result.html_body

    # Plain text body retains raw characters (safe for terminal/plain-text email)
    assert "<script>alert('xss')</script>" in result.text_body
    assert "Fix <critical> bug & review" in result.text_body


# 10. Source CSV files remain unchanged
def test_source_csv_files_remain_unchanged():
    contacts_path = Path("data/sample/contacts.csv")
    reminders_path = Path("data/sample/reminders.csv")

    def get_hash(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    h_contacts_before = get_hash(contacts_path)
    h_reminders_before = get_hash(reminders_path)

    # Execute full dataset personalization
    contacts = load_contacts_dict(contacts_path)
    reminders = load_reminders_list(reminders_path)
    results = personalize_dataset(contacts, reminders)
    assert len(results) == len(reminders) == 24

    assert get_hash(contacts_path) == h_contacts_before, "contacts.csv was modified!"
    assert get_hash(reminders_path) == h_reminders_before, "reminders.csv was modified!"


# 11. Generated output contains both HTML and plain-text bodies
def test_output_contains_both_html_and_text(sample_contact, sample_reminder):
    result = personalize_reminder(sample_contact, sample_reminder)
    assert len(result.html_body) > 100
    assert len(result.text_body) > 50
    assert "<!DOCTYPE html>" in result.html_body
    assert "---" in result.text_body


# 12. Invalid template keys produce a clear error
def test_invalid_template_key_produces_error(sample_contact):
    bad_reminder = Reminder(
        reminder_id="REM999",
        contact_id="CON001",
        reminder_type="Unknown",
        template_key="invalid_template_key",
        due_at="2027-01-01T00:00:00Z",
        status="pending",
        reference_id="REF",
        notes="Notes",
    )
    with pytest.raises(TemplateNotFoundError, match="Unsupported template key: 'invalid_template_key'"):
        personalize_reminder(sample_contact, bad_reminder)
