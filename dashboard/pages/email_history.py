"""Dashboard Email History Page

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Filterable email dispatch activity history and audit inspector.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from src.email_automation.config import load_config
from src.email_automation.insights import get_email_history_df
from src.email_automation.database import get_db_connection, DEFAULT_DB_PATH
from dashboard.components.tables import render_dataframe
from dashboard.components.theme import get_theme_colors


def render_email_history_page() -> None:
    """Renders the email dispatch history and audit inspector page."""
    c = get_theme_colors()
    config = load_config()

    st.markdown("## 📨 Email Dispatch History")
    st.markdown(
        '<div class="author-badge">Author: <strong>Akash Das</strong> | Dispatch Audit & Verification</div>',
        unsafe_allow_html=True,
    )

    # Mandatory SMTP operational notice
    st.info(
        "ℹ️ **Operational Verification Notice:** Under standard Gmail SMTP relaying protocols, a status of "
        "**'sent'** confirms successful protocol handshake and acceptance by `smtp.gmail.com` for onward delivery. "
        "It does **not** constitute proof of confirmed inbox placement or recipient read status."
    )

    # 1. Filter Controls
    col_search, col_status = st.columns([2, 1])
    with col_search:
        search_query = st.text_input("🔍 Search History", placeholder="Search by recipient, subject, or Reminder ID...")
    with col_status:
        statuses = ["All", "simulated", "sent", "failed", "delivery_unknown"]
        selected_status = st.selectbox("Dispatch Outcome", options=statuses, index=0)

    col_date1, col_date2 = st.columns(2)
    with col_date1:
        start_date = st.date_input("Filter from Due Date (Optional)", value=None)
    with col_date2:
        end_date = st.date_input("Filter to Due Date (Optional)", value=None)

    # 2. Retrieve history DataFrame (strictly dispatch attempts: simulated, sent, failed, delivery_unknown)
    df = get_email_history_df(
        db_path=DEFAULT_DB_PATH,
        status=selected_status,
        start_date=start_date,
        end_date=end_date,
        search_query=search_query,
    )

    st.markdown(f"**Showing {len(df)} dispatch records:**")
    render_dataframe(df, height=350)

    # 3. Message Body & Detail Inspector
    st.markdown("---")
    st.markdown("### 🔍 Prepared Email Inspector")
    
    if not df.empty:
        reminder_ids = df["Reminder ID"].tolist()
        selected_rem_id = st.selectbox(
            "Select a dispatched reminder to inspect its rendered email message:",
            options=reminder_ids,
        )

        with get_db_connection(DEFAULT_DB_PATH) as conn:
            prep_row = conn.execute(
                """
                SELECT p.reminder_id, p.recipient_name, p.recipient_email, p.subject,
                       p.text_body, p.html_body, p.prepared_at, r.status, r.dispatch_error
                FROM prepared_emails p
                JOIN reminders r ON p.reminder_id = r.reminder_id
                WHERE p.reminder_id = ?;
                """,
                [selected_rem_id],
            ).fetchone()

        if prep_row:
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                st.markdown(f"**Recipient:** {prep_row['recipient_name']} (`{prep_row['recipient_email']}`)")
                st.markdown(f"**Subject:** {prep_row['subject']}")
                st.markdown(f"**Prepared At:** `{prep_row['prepared_at']}`")
            with col_d2:
                st.markdown(f"**Status:** `{prep_row['status']}`")
                if prep_row['dispatch_error']:
                    st.markdown(f"**Error / Notes:** `{prep_row['dispatch_error']}`")

            with st.expander("📄 View Rendered Plain Text Body", expanded=False):
                st.code(prep_row["text_body"], language="text")

            with st.expander("🌐 View Rendered HTML Body Preview", expanded=False):
                st.components.v1.html(prep_row["html_body"], height=300, scrolling=True)


if __name__ == "__main__":
    from dashboard.components.theme import init_theme, apply_theme
    init_theme()
    apply_theme()
    render_email_history_page()
