# Email Template Architecture & Guide

**Project Name:** Email Automation & Reminder System  
**Project Author:** Akash Das  
**Development Environment:** Antigravity IDE (VS Code-based)  
**Project Lead & Reviewer:** ChatGPT  

---

## 1. Overview & Purpose
The email template system provides reusable, multi-part (HTML and plain-text) templates designed for business communications. Decoupled from the backend execution and scheduling engines, each template represents an independent design asset conforming to a strict placeholder contract.

All templates reside in [`templates/email_templates/`](file:///d:/Projects/Python/Email%20Automation%20%26%20Reminder%20System/templates/email_templates).

---

## 2. Template Key Mapping & Subject Lines

Each `template_key` found in [`data/sample/reminders.csv`](file:///d:/Projects/Python/Email%20Automation%20%26%20Reminder%20System/data/sample/reminders.csv) maps directly to an HTML and a plain-text asset pair:

| Template Key | HTML File | Plain-Text File | Standard Subject Line Format |
| :--- | :--- | :--- | :--- |
| **`meeting`** | `meeting_reminder.html` | `meeting_reminder.txt` | `Meeting Reminder: {notes} [Ref: #{reference_id}]` |
| **`payment`** | `payment_reminder.html` | `payment_reminder.txt` | `Payment Notice: Upcoming payment for invoice #{reference_id}` |
| **`deadline`** | `deadline_reminder.html` | `deadline_reminder.txt` | `Deadline Reminder: Action required for {notes} [Ref: #{reference_id}]` |
| **`follow_up`** | `follow_up_reminder.html` | `follow_up_reminder.txt` | `Follow-Up Request: Status update regarding {notes} [Ref: #{reference_id}]` |
| **`general`** | `general_reminder.html` | `general_reminder.txt` | `Notice: {reminder_type} update for {company} - Ref: #{reference_id}` |

---

## 3. Placeholder Specifications

Templates support dynamic substitution using standard Python `{placeholder}` syntax:

| Placeholder | Origin | Type | Required / Optional | Description | Example |
| :--- | :--- | :--- | :---: | :--- | :--- |
| `{first_name}` | Contact | String | **Required** | Recipient's first name | `Aarav` |
| `{last_name}` | Contact | String | Optional | Recipient's surname | `Sharma` |
| `{full_name}` | Contact | String | **Required** | Combined recipient name | `Aarav Sharma` |
| `{email}` | Contact | String | **Required** | Destination email address | `aarav.sharma@example.com` |
| `{department}` | Contact | String | **Required** | Recipient division / dept | `IT`, `Finance`, `Operations` |
| `{company}` | Contact | String | **Required** | Affiliated organization | `Apex Innovations` |
| `{reminder_type}` | Reminder | String | **Required** | High-level reminder type | `Task Deadline`, `Meeting` |
| `{due_at}` | Reminder | String | **Required** | Scheduled or deadline timestamp | `2027-01-10T10:00:00Z` |
| `{reference_id}` | Reminder | String | **Required** | Tracking or invoice code | `TSK-1001`, `INV-3001` |
| `{notes}` | Reminder | String | **Required** | Specific instruction or summary | `Submit Q1 upgrade plan` |

---

## 4. Technical Design Conventions

### HTML Format Standards
- **Client Compatibility**: Uses HTML table layouts with inline CSS styling compatible with major web, desktop, and mobile email clients (Gmail, Outlook, Apple Mail).
- **Responsive Layout**: Constrained to a standard `max-width: 600px` container with fluid table widths.
- **Visual Hierarchy**: Includes branded header blocks, structured key-value summary boxes, body guidance, and footers with recipient audit metadata.
- **Zero External Dependencies**: Contains no external image links, trackers, or JavaScript.

### Plain-Text Standards
- Identical information architecture formatted cleanly with uppercase section headers and bullet points.
- Suitable for terminal previews, screen readers, and email clients configured to display text-only payloads.

---

## 5. Security & Rendering Guidelines (Future Phases)
1. **HTML Escaping**: When Phase 6 (Email Personalization) executes template replacement, all user-supplied values (`notes`, `company`, etc.) must be HTML-escaped before insertion to prevent HTML injection attacks.
2. **Credential Safety**: Templates are strictly free of SMTP server configurations, app passwords, or environment tokens.
3. **MIME Construction**: In Phase 8, emails will be assembled as `multipart/alternative` containers encapsulating both `.txt` and `.html` alternatives.
