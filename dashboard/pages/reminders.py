"""Dashboard Reminders Page

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Filterable reminder schedule manager and safe interactive single-run dispatch trigger.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from src.email_automation.config import load_config
from src.email_automation.insights import get_all_reminders_df
from src.email_automation.database import get_db_connection, DEFAULT_DB_PATH
from src.email_automation.reminder_service import run_due_reminders_once
from src.email_automation.mailer import dispatch_ready_emails
from dashboard.components.tables import render_dataframe
from dashboard.components.theme import get_theme_colors


def render_reminders_page() -> None:
    """Renders the reminder schedule management page."""
    c = get_theme_colors()
    config = load_config()

    st.markdown("## ⏰ Reminder Schedule Management")
    st.markdown(
        '<div class="author-badge">Author: <strong>Akash Das</strong> | Schedule & Queue Preparation</div>',
        unsafe_allow_html=True,
    )

    # 1. Fetch distinct template keys
    with get_db_connection(DEFAULT_DB_PATH) as conn:
        tmpl_rows = conn.execute("SELECT DISTINCT template_key FROM reminders ORDER BY template_key;").fetchall()
    templates = ["All"] + [r[0] for r in tmpl_rows if r[0]]

    statuses = [
        "All",
        "pending",
        "ready",
        "processing",
        "simulated",
        "sent",
        "failed",
        "delivery_unknown",
    ]

    # 2. Filter Controls
    col_search, col_status, col_tmpl = st.columns([2, 1, 1])
    with col_search:
        search_query = st.text_input("🔍 Search Reminders", placeholder="Search by Reminder ID, Reference ID, Recipient...")
    with col_status:
        selected_status = st.selectbox("Status Filter", options=statuses, index=0)
    with col_tmpl:
        selected_tmpl = st.selectbox("Template Filter", options=templates, index=0)

    # 3. Retrieve filtered DataFrame
    df = get_all_reminders_df(
        db_path=DEFAULT_DB_PATH,
        status=selected_status,
        template_key=selected_tmpl,
        search_query=search_query,
    )

    st.markdown(f"**Showing {len(df)} matching reminder records:**")
    render_dataframe(df, height=380)

    st.markdown("---")

    # 4. Interactive Dispatch Trigger Section
    st.markdown("### 🚀 Interactive Dispatch Trigger")
    st.caption("Manually execute a single scheduling pass and dispatch cycle for all reminders currently due (due_at <= now).")

    is_dry = config.dry_run

    if is_dry:
        st.info("ℹ️ **Dry-Run Mode Active:** Reminder dispatch will be simulated safely with full personalization, validation, and database updates. No live SMTP transmission will take place.")
        confirm_live = False
    else:
        st.warning("⚠️ **CAUTION — LIVE SMTP MODE ACTIVE:** Reminders will transmit actual emails via `smtp.gmail.com` to recipient addresses.")
        confirm_live_check = st.checkbox("I understand and authorize live email transmission to real inboxes", value=False)
        confirm_live_phrase = st.text_input("Type 'CONFIRM LIVE SEND' to authorize:", value="", placeholder="CONFIRM LIVE SEND")
        confirm_live = confirm_live_check and (confirm_live_phrase.strip() == "CONFIRM LIVE SEND")

    btn_label = "🧪 Run Due Reminders (Simulation)" if is_dry else "⚡ Dispatch Due Reminders (Live)"
    
    if st.button(btn_label, type="primary"):
        if not is_dry and not confirm_live:
            st.error("Live dispatch refused: You must check the authorization box and type 'CONFIRM LIVE SEND'.")
        else:
            with st.spinner("Processing due reminders..."):
                try:
                    # Step 1: Claim due reminders & personalize
                    sched_summary = run_due_reminders_once(
                        db_path=DEFAULT_DB_PATH,
                    )
                    claimed_count = sched_summary.prepared

                    # Step 2: Dispatch ready emails
                    dispatch_summary = dispatch_ready_emails(
                        db_path=DEFAULT_DB_PATH,
                        config=config,
                        confirm_live_send=confirm_live,
                    )
                    dispatched_count = (
                        dispatch_summary.simulated if is_dry else dispatch_summary.smtp_accepted
                    )

                    st.success(
                        f"Execution completed successfully! Reminders claimed & prepared: **{claimed_count}**, "
                        f"Emails dispatched: **{dispatched_count}**."
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Error executing reminder dispatch: {str(e)}")


if __name__ == "__main__":
    from dashboard.components.theme import init_theme, apply_theme
    init_theme()
    apply_theme()
    render_reminders_page()
