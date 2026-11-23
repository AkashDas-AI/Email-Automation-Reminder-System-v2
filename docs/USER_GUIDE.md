# User & Operator Guide: Email Automation & Reminder System

**Project Name:** Email Automation & Reminder System  
**Author:** Akash Das  
**Development Environment:** Antigravity IDE (VS Code-based)  
**Lead Reviewer & Evaluator:** ChatGPT  
**Implementation Developer:** Antigravity Senior Developer  

---

## 1. System Requirements & Quick Start

### 1.1 Prerequisites
- **Python**: Version 3.11 or higher
- **Operating System**: Windows 10/11, Linux, or macOS
- **Environment**: Virtual environment (`.venv`) recommended
- **Dependencies**: Listed in `requirements.txt` (Streamlit, Pandas, Plotly, python-dotenv, pytest)

### 1.2 Environment Setup
1. Open terminal in the project root directory.
2. Activate the Python virtual environment:
   ```powershell
   # Windows PowerShell
   .\.venv\Scripts\Activate.ps1

   # Windows Command Prompt
   .\.venv\Scripts\activate.bat

   # macOS / Linux
   source .venv/bin/activate
   ```
3. Verify dependencies are installed:
   ```powershell
   python -m pip install -r requirements.txt
   ```
4. Configure environment variables in `.env` (copy from `.env.example` if not present):
   ```ini
   # Execution Safety Toggle (True = Simulation, False = Live SMTP)
   DRY_RUN=True

   # SQLite Database Location
   DATABASE_PATH=data/database/reminders.db

   # Email Template Directory
   TEMPLATES_DIR=templates/email_templates

   # SMTP Configuration (Optional when DRY_RUN=True)
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_SENDER_EMAIL=your_email@gmail.com
   SMTP_APP_PASSWORD=your_16_digit_app_password
   ```

---

## 2. Launching the System

The system provides two operational interfaces: an interactive **Streamlit Dashboard** and a **Command Line Interface (CLI)**.

### 2.1 Interactive Streamlit Dashboard (Recommended)
To launch the permanent Dark Mode web dashboard:
```powershell
.\.venv\Scripts\python.exe -m streamlit run dashboard/app.py
```
Or via the launcher script:
```powershell
.\.venv\Scripts\python.exe run_dashboard.py
```
The dashboard opens automatically in your default browser at `http://localhost:8501`.

### 2.2 Command-Line Interface (CLI)
To run a manual batch check and dispatch pass from the terminal:
```powershell
.\.venv\Scripts\python.exe main.py
```
This executes:
1. Database connectivity check and schema migration verification.
2. Temporal due-date check for pending reminders.
3. Personalization and template rendering for due items.
4. Two-phase gated dispatch (simulated in Dry-Run mode; live if configured).
5. Dual audit log recording in `logs/email_automation.log` and `activity_logs`.

---

## 3. Streamlit Dashboard Walkthrough

The dashboard contains seven dedicated operational pages in the left sidebar, permanently rendered in high-contrast dark theme (`#0F172A` deep navy canvas, `#1E293B` slate card panels, `#38BDF8` celestial cyan accents).

```
┌─────────────────────────────────────────────────────────────┐
│ 📧 Email Automation                                         │
│ Author: Akash Das                                          │
│                                                             │
│ ● Overview                                                  │
│ ○ Contacts                                                  │
│ ○ Reminders                                                 │
│ ○ Email History                                             │
│ ○ Insights & Analytics                                      │
│ ○ Reports                                                   │
│ ○ Settings & Diagnostics                                    │
└─────────────────────────────────────────────────────────────┘
```

### Page 1: Overview
- **Executive Metric Cards**: Real-time counts of Total Reminders, Pending Workload, Ready for Dispatch, and Simulated/Sent records.
- **Reminder Status Distribution**: Interactive Plotly donut chart displaying the breakdown of reminder states.
- **Dispatch Outcome Comparison**: Bar chart comparing successful simulations, SMTP transmissions, failures, and ambiguous deliveries.
- **Interactive Manual Dispatch Button**: Allows the operator to trigger an immediate check and dispatch cycle on demand.
- **Recent System Activity Stream**: Displays the latest 10 log entries with timestamps, severity indicators, and messages.

### Page 2: Contacts
- **Search & Filter Bar**: Filter contacts by name, email, department, or company.
- **Contact Directory Table**: Responsive tabular view displaying contact ID, full name, email, department, and company.
- **Contact Detail Inspector**: Select any contact from a dropdown to inspect their full profile and list all associated reminders with due dates and statuses.

### Page 3: Reminders
- **Multi-Criterion Filters**: Filter reminders by status (`pending`, `ready`, `simulated`, `sent`, `failed`), priority (`low`, `medium`, `high`, `urgent`), or category.
- **Reminder Operations Table**: Detailed grid showing reminder ID, recipient, task title, scheduled due date, priority badge, and current lifecycle state.
- **Live Template Preview Modal**: Select any reminder to preview the rendered email subject line and body with all `{placeholders}` populated.
- **Manual Reminder Creator**: Form to register a new reminder task for any contact with custom due date, priority, and template selection.

### Page 4: Email History
- **Dispatch Audit Log**: Full historical record of all email transmission attempts.
- **Status Filter**: Drill down into `simulated`, `sent`, `failed`, or `delivery_unknown` records.
- **Payload & Trace Inspector**: Expand any transaction to view the complete MIME subject, recipient, body, and underlying transport response.

### Page 5: Insights & Analytics (Phase 11 Engine)
- **Operational KPI Cards**: Total Attempted Dispatches, Realized Success Rate, and Failure Ratio.
- **Upcoming Actionable Workload**: Displays count of active actionable reminders (`pending` and `ready` scheduled for the future) strictly separated from past-due records.
- **Workload Timeline Distribution**: Visualizes reminders across time horizons (Past-Due, Due Today, Due Tomorrow, Next 7 Days, Beyond 7 Days).
- **Departmental Workload Breakdown**: Bar chart highlighting which departments have the heaviest notification volume (e.g., Engineering vs Marketing).
- **Automated Interpretation Cards**: Dynamic, narrative findings generated by the `InterpretationEngine` evaluating delivery health, workload peaks, and actionable recommendations.

### Page 6: Reports & Exports
- **CSV Data Exporters**: One-click download buttons to export current datasets as formatted CSV files:
  - `export_reminders.csv`
  - `export_contacts.csv`
  - `export_activity_logs.csv`
- **System Health Report**: Generates a consolidated markdown and text summary of operational metrics.

### Page 7: Settings & System Diagnostics
- **Configuration Overview**: Displays active execution mode (`DRY_RUN` status), database path, templates directory, and SMTP connection parameters.
- **SQLite Database Diagnostics**: Runs `PRAGMA integrity_check;` and reports schema version, WAL journal mode status, and record counts for all database tables.

---

## 4. Safe Sending Guidelines & Troubleshooting

### 4.1 Safety First: Dry-Run Mode
- Always leave `DRY_RUN=True` during development, testing, and UI exploration.
- In Dry-Run mode, all email templates are rendered, validated, and logged exactly as they would be sent, but no external network connection is opened.
- To enable live sending, you must explicitly set `DRY_RUN=False` in `.env` and supply valid Gmail App Passwords.

### 4.2 Troubleshooting Common Issues

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| `Port 8501 is already in use` | Another Streamlit process is running. | Run `streamlit run dashboard/app.py --server.port 8502` or terminate the lingering process via Task Manager. |
| `sqlite3.OperationalError: database is locked` | Another process holds an exclusive lock. | SQLite is configured in WAL mode with a 5000ms busy timeout. Ensure long-running transactions are committed. |
| `SMTPAuthenticationError (535)` | Gmail rejected your credentials. | Use a 16-character Google App Password (not your standard account password). Ensure 2-Step Verification is enabled. |
| `StreamlitInvalidHeightError` | Streamlit received an invalid height argument. | All tables are routed through `dashboard/components/tables.py` with sanitized auto height; ensure latest component code is used. |
| Missing Placeholders Error | Template references variables not present in contact record. | Verify that template `{placeholders}` match contact schema fields (`name`, `email`, `department`, `company`, `due_date`, `task_name`). |
