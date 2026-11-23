# Module Specifications

**Project Name:** Email Automation & Reminder System  
**Project Author:** Akash Das  
**Development Environment:** Antigravity IDE (VS Code-based)  
**Project Lead & Reviewer:** ChatGPT  

---

## 1. Modular Directory & Package Architecture

The architecture maintains strict separation of concerns across core business logic, web presentation, persistence, templates, and outputs:

```text
Email Automation & Reminder System/
│
├── data/
│   ├── sample/                      # Sample contact & reminder CSV datasets
│   └── database/                    # SQLite database persistent storage
│
├── templates/
│   └── email_templates/            # Reusable text & HTML email templates
│
├── src/
│   └── email_automation/           # Core application package
│       ├── __init__.py              # Package entry & metadata
│       ├── config.py                # Environment & configuration loader
│       ├── database.py              # Centralized SQLite manager & queries
│       ├── models.py                # Data classes, entities & schemas
│       ├── validator.py             # Schema & email validation logic
│       ├── importer.py              # CSV ingestion via Pandas
│       ├── personalization.py       # Dynamic placeholder template engine
│       ├── mailer.py                # Dry-run simulator & SMTP dispatcher
│       ├── reminder_service.py      # Business process orchestrator
│       ├── scheduler.py             # Background scheduling engine
│       ├── report_generator.py      # CSV export & audit generator
│       └── insights.py              # Performance metrics & analytics
│
├── dashboard/                       # Streamlit web interface (Mandatory Phase 10)
│   ├── app.py                       # Multi-page dashboard entry point
│   ├── pages/                       # Functional sub-pages
│   │   ├── contacts.py              # Recipient contact management
│   │   ├── reminders.py             # Reminder queue & manual trigger controls
│   │   ├── email_history.py         # Delivery audit & log viewer
│   │   ├── reports.py               # Downloadable CSV reports
│   │   └── insights.py              # KPIs and analytics visualizations
│   └── components/                  # Reusable Streamlit UI widgets
│       ├── metrics.py               # KPI metric cards
│       ├── charts.py                # Plotly chart helpers
│       └── tables.py                # Styled dataframe helpers
│
├── outputs/
│   ├── reports/                     # Generated activity CSV reports
│   └── exports/                     # Data exports
│
├── logs/                            # Application runtime logs
│
├── images/
│   ├── dashboard/                   # UI screenshots
│   └── architecture/                # System diagrams
│
├── docs/                            # Living project documentation
│   └── screenshots/
│
├── tests/                           # Unit & integration test suite
│
├── .venv/                           # Python 3.11 virtual environment
├── .vscode/settings.json            # Workspace interpreter configuration
├── main.py                          # CLI application entry point
├── run_dashboard.py                 # Streamlit application launcher
├── requirements.txt                 # Pinned dependencies
├── README.md                        # Root project overview
├── CONTRIBUTING.md                  # Development guidelines
├── LICENSE                          # Project license
├── .gitignore                       # Repository exclusion rules
└── .env.example                     # Environment template without secrets
```

---

## 2. Core Service Module Responsibilities

| Module | Core Responsibility | Planned Key Classes / Functions |
| :--- | :--- | :--- |
| `config.py` | Loads and validates `.env` settings; provides application constants | `Config`, `get_settings()` |
| `database.py` | Manages SQLite connection pooling, tables, and CRUD operations | `DatabaseManager`, `get_db_connection()` |
| `models.py` | Typed dataclasses representing core entities | `Contact`, `Reminder`, `DeliveryLog` |
| `validator.py` | Validates email syntax, mandatory fields, and dates | `validate_contact()`, `validate_reminder()` |
| `importer.py` | Parses and normalizes input CSV datasets using Pandas | `load_contacts_csv()`, `load_reminders_csv()` |
| `personalization.py` | Performs token substitution (`{{name}}`, `{{task}}`, etc.) | `render_template()`, `build_email_content()` |
| `mailer.py` | Simulates sending in dry-run mode or dispatches via SMTP | `EmailSender`, `DryRunMailer`, `SMTPMailer` |
| `reminder_service.py`| Evaluates due reminders, invokes mailer, updates DB | `ReminderService`, `process_due_reminders()` |
| `scheduler.py` | Executes periodic check loops independently of UI | `ReminderScheduler`, `start_scheduler()` |
| `report_generator.py`| Queries SQLite history and formats CSV reports | `generate_delivery_report()`, `export_csv()` |
| `insights.py` | Aggregates DB metrics for success rates and department breakdown | `compute_kpis()`, `get_status_distribution()` |
