# SMTP Configuration & Security Guide

**Project Name:** Email Automation & Reminder System  
**Project Author:** Akash Das  
**Development Environment:** Antigravity IDE (VS Code-based)  
**Project Lead & Reviewer:** ChatGPT  

---

## 1. Overview & Purpose of SMTP
Simple Mail Transfer Protocol (SMTP) is the internet standard communication protocol for electronic mail transmission. In this system, SMTP enables the application to authenticate against a mail transport server and relay outbound reminder messages to recipient inboxes.

To ensure safety during academic development and automated testing, the system provides a dual-mode dispatch architecture:
- **Dry-Run Mode (`DRY_RUN=true`)**: Safely simulates message assembly and delivery logging without touching external network infrastructure or requiring sensitive credentials.
- **Live SMTP Mode (`DRY_RUN=false`)**: Connects to Gmail's secure SMTP relay over TLS/STARTTLS to dispatch actual emails.

---

## 2. Gmail SMTP Protocol Specifications

| Parameter | Configuration Value | Description |
| :--- | :--- | :--- |
| **Server Host** | `smtp.gmail.com` | Google's public outgoing mail server |
| **Port** | `587` | Submission port initiating cleartext before TLS upgrade |
| **Encryption** | **STARTTLS** | Upgrades the connection to TLS 1.3 encryption before credentials are sent |
| **Authentication** | Username + App Password | RFC 4954 SASL authentication |

> [!IMPORTANT]
> **Port 587 with STARTTLS**: The standard secure submission port for client applications. The client connects and issues the `STARTTLS` command, ensuring that all authentication data and message payloads are encrypted in transit.

---

## 3. Environment Variables Reference

All runtime parameters are loaded from environment variables or a local, uncommitted `.env` file via `python-dotenv`:

| Variable Name | Type | Default Value | Required in Dry-Run | Required in Live SMTP | Description |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `DRY_RUN` | Boolean | `true` | No | Yes | Operational safety toggle. When `true`, no emails are sent. |
| `SMTP_HOST` | String | `smtp.gmail.com` | No | Yes | Outgoing mail server address. |
| `SMTP_PORT` | Integer | `587` | No | Yes | Connection port (1–65535, standard: 587). |
| `SMTP_USERNAME`| String | None | No | **Yes** | Sender Gmail address (e.g. `your_account@gmail.com`). |
| `SMTP_PASSWORD`| String | None | No | **Yes** | 16-character Gmail App Password. |
| `EMAIL_FROM` | String | None | No | **Yes** | Originating `From` header address. |
| `EMAIL_FROM_NAME` | String | `"Email Automation Reminder System"` | No | No | Friendly sender display name. |
| `TIMEZONE` | String | `"UTC"` | No | No | Application reference timezone. |

---

## 4. Local Gmail App Password Setup (For Author Akash Das)

To configure the project for real email dispatching in subsequent phases, the author must generate a dedicated Gmail App Password. **Never use your standard Google account login password.**

### Step-by-Step Instructions:
1. **Enable 2-Step Verification**:
   - Go to [Google Account Security Settings](https://myaccount.google.com/security).
   - Under *"How you sign in to Google"*, ensure **2-Step Verification** is turned ON.
2. **Generate an App Password**:
   - Search for **"App passwords"** in the Google Account search bar.
   - Enter an application name (e.g., `Email Reminder System`).
   - Click **Create**. Google will generate a unique 16-character passcode (e.g., `abcd efgh ijkl mnop`).
3. **Configure Local `.env`**:
   - Copy `.env.example` to `.env` in the repository root:
     ```powershell
     Copy-Item .env.example .env
     ```
   - Open `.env` and fill in your details:
     ```env
     DRY_RUN=false
     SMTP_HOST=smtp.gmail.com
     SMTP_PORT=587
     SMTP_USERNAME=your_email@gmail.com
     SMTP_PASSWORD=abcdefghijklmnop
     EMAIL_FROM=your_email@gmail.com
     ```
   - Save the file.

---

## 5. Security & Credential Isolation Rules

- **Zero Git Tracking**: `.gitignore` strictly excludes `.env` and all `.env.*` variants while keeping `.env.example` tracked.
- **Log Masking**: The `AppConfig` class overrides `__repr__` to mask `smtp_password` as `********`. Secrets are never emitted to logs or terminal output.
- **Exception Sanitization**: If credentials are missing in SMTP mode, `ConfigurationError` reports the names of the missing variables without exposing any existing secret tokens.
- **No Third-Party Sharing**: Never share or paste actual App Passwords into chats, commits, or issue trackers.

---

## 6. Configuration Validation Workflow

The configuration is verified programmatically using `src/email_automation/config.py`:
1. `load_config()` reads environment variables.
2. If `DRY_RUN=true`: Validates port syntax and host defaults; allows missing credentials.
3. If `DRY_RUN=false`: Asserts that `SMTP_USERNAME`, `SMTP_PASSWORD`, and `EMAIL_FROM` are non-empty strings.
4. `validate_smtp_readiness()` checks that connection metadata is structurally sound.

---

## 7. Why Actual Email Sending is Reserved for Phase 8
- Phase 5 establishes the configuration foundation and security boundary.
- Phase 6 will implement contact-reminder template personalization.
- Phase 7 will implement automated scheduling.
- **Phase 8** will implement the dual-dispatch mailer (`src/email_automation/mailer.py`), incorporating dry-run simulation and actual SMTP delivery with retry handling.
