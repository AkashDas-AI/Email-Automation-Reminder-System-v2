"""Dashboard Contacts Page

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Searchable, filterable contacts directory and detail inspector.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from src.email_automation.config import load_config
from src.email_automation.insights import get_all_contacts_df
from src.email_automation.database import get_db_connection, DEFAULT_DB_PATH
from dashboard.components.tables import render_dataframe
from dashboard.components.theme import get_theme_colors


def render_contacts_page() -> None:
    """Renders the interactive contacts directory page."""
    c = get_theme_colors()
    config = load_config()

    st.markdown("## 👥 Recipient Contacts Directory")
    st.markdown(
        '<div class="author-badge">Author: <strong>Akash Das</strong> | Contact Database Management</div>',
        unsafe_allow_html=True,
    )

    # 1. Fetch distinct departments and companies for dropdowns
    with get_db_connection(DEFAULT_DB_PATH) as conn:
        dept_rows = conn.execute("SELECT DISTINCT department FROM contacts WHERE department IS NOT NULL ORDER BY department;").fetchall()
        comp_rows = conn.execute("SELECT DISTINCT company FROM contacts WHERE company IS NOT NULL ORDER BY company;").fetchall()

    departments = ["All"] + [r[0] for r in dept_rows if r[0]]
    companies = ["All"] + [r[0] for r in comp_rows if r[0]]

    # 2. Filter Controls
    col_search, col_dept, col_comp = st.columns([2, 1, 1])
    with col_search:
        search_query = st.text_input("🔍 Search Contacts", placeholder="Search by name or email...")
    with col_dept:
        selected_dept = st.selectbox("Department", options=departments, index=0)
    with col_comp:
        selected_comp = st.selectbox("Company", options=companies, index=0)

    # 3. Retrieve filtered contacts DataFrame
    df = get_all_contacts_df(
        db_path=DEFAULT_DB_PATH,
        search_query=search_query,
        department=selected_dept,
        company=selected_comp,
    )

    st.markdown(f"**Showing {len(df)} matching contact records:**")
    render_dataframe(df, height=350)

    # 4. Contact Detail & Associated Reminders Inspector
    st.markdown("---")
    st.markdown("### 🔎 Contact Detail Inspector")
    
    if not df.empty:
        contact_ids = df["Contact ID"].tolist()
        contact_labels = [f"{row['Contact ID']} — {row['Name']} ({row['Email']})" for _, row in df.iterrows()]
        
        selected_idx = st.selectbox(
            "Select a contact to view full profile and associated reminders:",
            options=range(len(contact_ids)),
            format_func=lambda i: contact_labels[i],
        )

        selected_id = contact_ids[selected_idx]
        selected_row = df[df["Contact ID"] == selected_id].iloc[0]

        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            st.markdown(f"**Name:** {selected_row['Name']}")
            st.markdown(f"**Email:** `{selected_row['Email']}`")
        with col_c2:
            st.markdown(f"**Department:** {selected_row['Department']}")
            st.markdown(f"**Company:** {selected_row['Company']}")
        with col_c3:
            st.markdown(f"**Contact ID:** `{selected_row['Contact ID']}`")
            st.markdown(f"**Created At:** {selected_row['Created At']}")

        # Fetch associated reminders
        with get_db_connection(DEFAULT_DB_PATH) as conn:
            rem_df = pd.read_sql_query(
                """
                SELECT reminder_id AS "Reminder ID", reminder_type AS "Type", template_key AS "Template",
                       due_at AS "Due At (UTC)", status AS "Status", notes AS "Notes"
                FROM reminders
                WHERE contact_id = ?
                ORDER BY due_at ASC;
                """,
                conn,
                params=[selected_id],
            )
        
        st.markdown(f"**Associated Reminders ({len(rem_df)}):**")
        render_dataframe(rem_df)


if __name__ == "__main__":
    from dashboard.components.theme import init_theme, apply_theme
    init_theme()
    apply_theme()
    render_contacts_page()
