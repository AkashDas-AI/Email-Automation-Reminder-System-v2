# Streamlit Dashboard Integration Guide

**Project:** Email Automation & Reminder System  
**Author:** Akash Das  
**Role:** Senior Developer  
**Current Phase:** Phase 10 — Streamlit Dashboard Integration  
**Status:** Completed & Verified  

---

## 1. Executive Summary

Phase 10 delivers a comprehensive, interactive, and high-performance **Streamlit Dashboard** for the Email Automation & Reminder System. The dashboard provides an intuitive, browser-based graphical user interface (GUI) allowing operators to inspect contacts, monitor reminder schedules, review dispatch histories, analyze operational performance metrics with interactive Plotly visualizations, generate and export certified CSV reports, and execute database diagnostics.

The dashboard integrates directly with the existing SQLite persistent store (`data/database/reminders.db`) and core backend services without duplicating business logic, modifying underlying data schemas, or compromising security.

### Key Architectural Highlights:
- **Single, Permanent Dark Mode Architecture**: Operates exclusively in a permanent, high-contrast Dark Mode across all seven pages with zero user-facing theme toggles, Light Mode artifacts, or alternative themes.
- **7 Modular Dashboard Pages**:
  1. `Overview`: 8-metric KPI grid, operational status indicators, donut status distribution, dispatch outcome comparison, and recent activity log feed.
  2. `Contacts`: Searchable and filterable recipient directory (by search query, department, company) with associated reminder inspection.
  3. `Reminders`: Real-time schedule monitoring across all 7 statuses, template filtering, and safe interactive dispatch trigger.
  4. `Email History`: Detailed audit log strictly restricted to dispatch attempts (`simulated`, `sent`, `failed`, `delivery_unknown`) with rendered message inspection (HTML/plain text preview) and mandatory SMTP relay disclaimer.
  5. `Insights & Analytics`: In-depth analytical visualizations (Plotly) covering status distributions, outcome comparisons, department distributions, template usage, and audit timeline.
  6. `Reports`: Interactive generation, in-browser preview, and certified CSV export (`st.download_button`) for all 4 core system reports.
  7. `Settings & Diagnostics`: System configuration review, safe masked credentials display, SQLite WAL schema diagnostics, foreign key integrity checks, and sample CSV re-synchronization.
- **Strict Safety Invariants**:
  - Zero background daemon threads (`ContinuousScheduler`) started automatically on dashboard launch.
  - Strict Dry-Run simulation enforcement by default. Live SMTP mode requires explicit, double-gated checkbox confirmation.
  - Zero external network connections during unit tests.

---

## 2. Launching the Dashboard

The dashboard can be launched flexibly using any of the following supported commands:

```powershell
# Method 1: Using the standalone Python launcher
.\.venv\Scripts\python.exe run_dashboard.py

# Method 2: Using the Streamlit CLI with run_dashboard.py
.\.venv\Scripts\python.exe -m streamlit run run_dashboard.py

# Method 3: Direct Streamlit CLI invocation targeting app.py
.\.venv\Scripts\python.exe -m streamlit run dashboard/app.py
```

Upon launch, Streamlit binds to the local interface (default `http://localhost:8501`) and opens the dashboard in Dark Mode. All three launch methods are verified and supported without nested process issues.

---

## 3. Theme System Architecture

The dashboard features a centralized, fixed Dark Mode styling architecture located in `dashboard/components/theme.py`:

```
┌────────────────────────────────────────────────────────┐
│             Permanent Dark Mode Architecture           │
│                                                        │
│  [ .streamlit/config.toml ]  ──> Native base="dark"    │
│                                                        │
│  [ DARK_PALETTE in theme.py ]                          │
│         │                                              │
│         ├──> Scoped .stApp & Sidebar background/colors │
│         ├──> Custom .kpi-card & .status-pill styles   │
│         └──> Plotly Template ('plotly_dark')           │
└────────────────────────────────────────────────────────┘
```

### Theme Palette Specifications:

| Palette Key | Dark Mode Hex | Usage |
| :--- | :--- | :--- |
| **`bg`** | `#0E1117` | Main application background |
| **`card_bg`** | `#1A1F2C` | Metric and content card background |
| **`card_border`** | `#2D3748` | Structural dividers and container borders |
| **`text`** | `#F1F5F9` | Primary heading and body typography |
| **`text_muted`** | `#94A3B8` | Labels, captions, and secondary metadata |
| **`primary`** | `#3B82F6` | Active highlights, focus borders, primary buttons |
| **`success`** | `#10B981` | Success notifications and sent outcome pills |
| **`warning`** | `#F59E0B` | In-flight / processing indicators |
| **`danger`** | `#EF4444` | Terminal dispatch errors |
| **`plotly_template`** | `"plotly_dark"` | Plotly figure rendering template |

---

## 4. Multi-Page Functional Breakdown

### 4.1 Overview (`dashboard/pages/overview.py`)
- **System Health Status Banner**: Displays active dispatch mode (`DRY-RUN` vs `LIVE`), connected database version (`v9`), and scheduler readiness.
- **8 Primary KPI Metric Cards**:
  1. *Total Contacts*: Total registered recipients in the database.
  2. *Total Reminders*: Cumulative volume across all reminder statuses.
  3. *Attempted Dispatches*: Strictly $\text{Simulated} + \text{Sent} + \text{Failed}$.
  4. *Dispatch Success Rate*: $\frac{\text{Simulated} + \text{Sent}}{\text{Attempted}} \times 100\%$.
  5. *Simulated (Dry-Run)*: Successfully simulated dispatches.
  6. *Sent (SMTP Accepted)*: Dispatches accepted by `smtp.gmail.com`.
  7. *Failed Dispatches*: Definite, non-retried terminal dispatch errors.
  8. *Pipeline & Unknown*: Current queue backlog (`Pending` + `Ready` + `Delivery Unknown`).
- **Charts & Feeds**:
  - Status Distribution donut chart.
  - Dispatch Outcomes comparative bar chart.
  - Live activity feed showing the 10 most recent audit events with severity and timestamp.

### 4.2 Contacts Directory (`dashboard/pages/contacts.py`)
- **Real-Time Filtering**: Dynamic text search across recipient names and email addresses.
- **Categorical Dropdowns**: Filter by Department (Engineering, Marketing, HR, Finance, etc.) and Company.
- **Contact Inspector**: Select any contact from the interactive dropdown to view their detailed profile attributes and full history of associated reminders.

### 4.3 Reminder Schedule Management (`dashboard/pages/reminders.py`)
- **Schedule Table**: Displays all reminders joined with recipient names, email addresses, due timestamps (UTC), template keys, statuses, and error notes.
- **Multi-Parameter Filtering**: Filter by reminder status (`All`, `pending`, `ready`, `processing`, `simulated`, `sent`, `failed`, `delivery_unknown`), template key, or query string.
- **Interactive Manual Dispatch Trigger**:
  - Safely initiates a single scheduler claim pass (`run_due_reminders_once()`) and dispatch cycle (`dispatch_ready_emails()`).
  - Dry-run mode executes simulations safely without external network calls.
  - Live mode requires explicit confirmation via an authorization checkbox.
  - Instantly refreshes database metrics and UI upon completion.

### 4.4 Email Dispatch History (`dashboard/pages/email_history.py`)
- **Strict Attempt Filter**: Restricted exclusively to records that reached a dispatch attempt (`simulated`, `sent`, `failed`, `delivery_unknown`). Non-attempted reminders (`pending`, `ready`, `processing`) are strictly excluded.
- **Mandatory SMTP Notice**: Prominently warns operators that `sent` denotes acceptance by `smtp.gmail.com` for relay, not guaranteed recipient inbox placement.
- **Date Range & Status Filters**: Filter history by UTC date range or outcome.
- **Rendered Message Inspector**: Expand any historical dispatch record to inspect its plain text body or render its responsive HTML body inside a secure iframe component.

### 4.5 Insights & Analytics (`dashboard/pages/insights.py`)
- **Interactive Plotly Charts**:
  - *Reminder Status Breakdown*: Donut chart displaying proportions across all 7 statuses.
  - *Dispatch Outcomes Comparison*: Comparative bar chart of Simulated, Sent, Failed, and Delivery Unknown.
  - *Reminders by Department*: Horizontal bar chart highlighting recipient distribution.
  - *Reminders by Template Key*: Bar chart illustrating template utilization.
  - *Audit Events by Type*: Bar chart tracking activity log frequencies.
- **Mathematical Transparency Table**: Displays exact counts and role in calculations for all system entities.

### 4.6 Report Generation & Export (`dashboard/pages/reports.py`)
- **Supported Export Types**:
  1. *Email Activity Report*
  2. *Reminder Status Count Report*
  3. *Activity History Audit Report*
  4. *Reminder Details Report*
- **One-Click In-Browser Download**: Powered by `st.download_button`, allowing instantaneous CSV downloads with ISO-timestamped filenames.
- **Data Preview**: In-browser preview table rendering the generated report before download.

### 4.7 Settings & System Diagnostics (`dashboard/pages/settings.py`)
- **Configuration Review**: Displays operational parameters including execution mode, database path, templates directory, log file location, and SMTP host/port.
- **Safe Credential Masking**: Sender email is masked (`a***h@example.com`) and passwords are unconditionally masked (`••••••••••••`).
- **SQLite Diagnostics**:
  - Active schema version verification (`Version 9`).
  - Table row counts (`contacts`, `reminders`, `prepared_emails`, `activity_logs`).
  - One-click SQLite integrity verification running `PRAGMA foreign_key_check;` and `PRAGMA integrity_check;`.
- **Sample Synchronization**: One-click re-synchronization of sample contacts and reminders from `data/sample/contacts.csv` and `data/sample/reminders.csv`.

---

## 5. Verification & Testing

The dashboard integration is verified by 16 comprehensive unit and integration tests in `tests/test_dashboard.py`, bringing the total project test suite to **106 tests (100% passing)**:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard.py -v
```

### Verified Test Cases:
1. `test_theme_manager_permanent_dark_mode`: Confirms the dashboard permanently operates in Dark Mode with zero Light Mode artifacts.
2. `test_get_system_kpis_strict_calculation`: Enforces Attempted formula invariants and excludes pending/ready/processing/unknown.
3. `test_get_all_contacts_df`: Validates contacts retrieval with name, department, and company filters.
4. `test_get_all_reminders_df`: Validates reminders retrieval with status, template, and text filters.
5. `test_get_email_history_df_restricts_to_dispatch_outcomes`: Verifies email history excludes non-attempted states.
6. `test_get_activity_timeline_df`: Verifies activity history retrieval and limit parameters.
7. `test_chart_generators_render_figures`: Verifies all Plotly chart generators produce valid Figure instances.
8. `test_email_masking_helper`: Ensures credential masking protects email addresses in UI displays.
9. `test_safety_invariants_no_automatic_scheduler_or_smtp`: Confirms dashboard startup does not launch background threads or make network calls.
10. `test_manual_dispatch_safeguards_dry_run_simulation`: Confirms dry-run simulation performs zero SMTP network transmissions and transitions reminders to `simulated`.
11. `test_manual_dispatch_safeguards_live_requires_explicit_confirmation`: Verifies that live mode execution strictly raises `ConfigurationError` without explicit confirmation.
12. `test_manual_dispatch_safeguards_missing_credentials_refused`: Confirms live sending with confirmation is refused if credentials are missing.
13. `test_manual_dispatch_safeguards_allowlist_enforced`: Validates recipient allowlist rejection and failure recording.
14. `test_manual_dispatch_safeguards_repeated_clicks_idempotent`: Confirms repeated clicks process zero items and prevent duplicate sends.
15. `test_manual_dispatch_safeguards_delivery_unknown_not_retried`: Validates that ambiguous delivery records are never automatically retried.
16. `test_settings_data_sync_preserves_inflight_and_completed_records`: Ensures sample CSV re-synchronization updates only `pending` records and protects all active/terminal lifecycle states.
