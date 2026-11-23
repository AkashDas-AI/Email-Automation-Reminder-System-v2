"""Dashboard Settings Page

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Displays system configuration, runs database diagnostics, and manages sample sync.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from pathlib import Path

from src.email_automation.config import load_config
from src.email_automation.database import get_db_connection, import_or_sync_csv, DEFAULT_DB_PATH
from dashboard.components.tables import render_dataframe
from dashboard.components.theme import get_theme_colors


def mask_email(email: str) -> str:
    """Masks an email address for safe display."""
    if not email or "@" not in email:
        return "Not configured"
    user, domain = email.split("@", 1)
    if len(user) <= 2:
        masked_user = user[0] + "*"
    else:
        masked_user = user[0] + "*" * (len(user) - 2) + user[-1]
    return f"{masked_user}@{domain}"


def render_settings_page() -> None:
    """Renders the settings and system diagnostics page."""
    c = get_theme_colors()
    config = load_config()

    st.markdown("## ⚙️ Settings & System Diagnostics")
    st.markdown(
        '<div class="author-badge">Author: <strong>Akash Das</strong> | System Administration & Integrity</div>',
        unsafe_allow_html=True,
    )

    # 1. System Configuration Overview
    st.markdown("### 🛠️ Configuration Overview")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.markdown(f"**Execution Mode:** {'🧪 Dry-Run (Simulation)' if config.dry_run else '⚡ Live SMTP'}")
        st.markdown(f"**Database Path:** `{DEFAULT_DB_PATH}`")
        st.markdown(f"**Templates Directory:** `templates/email_templates`")
        st.markdown(f"**Log File:** `{config.log_file}`")

    with col_c2:
        st.markdown(f"**SMTP Host:** `{config.smtp_host}`")
        st.markdown(f"**SMTP Port:** `{config.smtp_port}` (STARTTLS)")
        st.markdown(f"**Sender Email:** `{mask_email(config.email_from or config.smtp_username or '')}`")
        pw_status = "•••••••••••• (Configured securely)" if config.smtp_password else "Not configured"
        st.markdown(f"**App Password:** `{pw_status}`")

    st.markdown("---")

    # 2. Database Diagnostics & Integrity Check
    st.markdown("### 🩺 Database Diagnostics & Integrity")
    
    with get_db_connection(DEFAULT_DB_PATH) as conn:
        schema_ver = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1;").fetchone()
        version_num = schema_ver[0] if schema_ver else 9

        counts = {
            "Contacts": conn.execute("SELECT count(*) FROM contacts;").fetchone()[0],
            "Reminders": conn.execute("SELECT count(*) FROM reminders;").fetchone()[0],
            "Prepared Emails": conn.execute("SELECT count(*) FROM prepared_emails;").fetchone()[0],
            "Activity Logs": conn.execute("SELECT count(*) FROM activity_logs;").fetchone()[0],
        }

    st.markdown(f"**Active Database Schema:** Version `{version_num}` (SQLite WAL Mode)")

    df_counts = pd.DataFrame(list(counts.items()), columns=["Table Entity", "Row Count"])
    render_dataframe(df_counts)

    if st.button("Run SQLite Integrity Verification"):
        with get_db_connection(DEFAULT_DB_PATH) as conn:
            fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
            integrity_res = conn.execute("PRAGMA integrity_check;").fetchall()

        if not fk_violations and integrity_res and integrity_res[0][0] == "ok":
            st.success("✅ Database integrity verification passed: 0 foreign key violations, PRAGMA check: OK.")
        else:
            st.error(f"Integrity check found issues: violations={fk_violations}, status={integrity_res}")

    st.markdown("---")

    # 3. Sample CSV Data Synchronization
    st.markdown("### 🔄 Data Synchronization")
    st.markdown(
        """
        Re-synchronize the database with baseline sample datasets (`data/sample/contacts.csv` and `data/sample/reminders.csv`):
        - **Contacts:** Inserts new contacts and updates profile fields (department, company).
        - **Reminders:** Inserts new reminders and updates `pending` reminder timestamps and metadata.
        - **Integrity Guarantee:** In-flight or completed reminders (`ready`, `processing`, `simulated`, `sent`, `failed`, `delivery_unknown`), prepared emails, and audit logs are strictly preserved and never overwritten.
        """
    )

    confirm_sync = st.checkbox("I understand and confirm synchronization from sample CSVs", value=False)

    if st.button("Synchronize from Sample CSVs", type="secondary"):
        if not confirm_sync:
            st.warning("Synchronization halted: Please check the confirmation checkbox above before proceeding.")
        else:
            try:
                contacts_synced, reminders_synced = import_or_sync_csv(
                    db_path=DEFAULT_DB_PATH,
                    contacts_csv="data/sample/contacts.csv",
                    reminders_csv="data/sample/reminders.csv",
                )
                st.success(f"Synchronization successful! Synced **{contacts_synced}** contacts and **{reminders_synced}** reminders.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to synchronize CSVs: {e}")


if __name__ == "__main__":
    from dashboard.components.theme import init_theme, apply_theme
    init_theme()
    apply_theme()
    render_settings_page()
