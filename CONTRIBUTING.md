# Contributing Guidelines

**Project:** Email Automation & Reminder System  
**Author:** Akash Das  

Thank you for reviewing and contributing to this project. This repository follows structured software engineering standards tailored for academic evaluation, portfolio presentation, and production maintainability.

---

## 1. Development Principles
- **Virtual Environment**: All development must use the local `.venv` environment. Never install packages globally.
- **Separation of Concerns**: Keep business logic in `src/email_automation/`, dashboard views in `dashboard/`, and tests in `tests/`.
- **Shared Architecture**: The CLI and Streamlit dashboard must operate on the same shared services and SQLite database.
- **Dry-Run Safety**: Dry-run simulation must remain the default operational mode. Never commit real email credentials.

---

## 2. Coding Standards
- Write modular, readable, and typed Python code following PEP 8.
- Every module must include docstrings explaining its purpose and author.
- Ensure all tests pass via `pytest tests/` before proposing changes.
- Keep `.gitignore` updated so that `.venv/`, `.env`, database files, and temporary logs are never staged.
