"""Dashboard Reports Page

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Generates, previews, and exports certified CSV operational reports.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime

from src.email_automation.config import load_config
from src.email_automation.database import DEFAULT_DB_PATH
from src.email_automation.report_generator import (
    generate_email_activity_report,
    generate_reminder_status_report,
    generate_activity_history_report,
    generate_reminder_details_report,
)
from dashboard.components.tables import render_dataframe
from dashboard.components.theme import get_theme_colors


def render_reports_page() -> None:
    """Renders the report generation and CSV export interface."""
    c = get_theme_colors()
    config = load_config()

    st.markdown("## 📑 Report Generation & Export")
    st.markdown(
        '<div class="author-badge">Author: <strong>Akash Das</strong> | Certified Operational Reporting</div>',
        unsafe_allow_html=True,
    )

    report_types = [
        "Email Activity Report",
        "Reminder Status Count Report",
        "Activity History Audit Report",
        "Reminder Details Report",
    ]

    selected_report = st.selectbox("Select Report to Generate", options=report_types, index=0)

    # Optional Filter inputs depending on report type
    start_date = None
    end_date = None
    if selected_report in ["Email Activity Report"]:
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            start_date = st.date_input("Start Date Filter (Optional)", value=None)
        with col_d2:
            end_date = st.date_input("End Date Filter (Optional)", value=None)

    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        generate_clicked = st.button("Generate & Preview", type="primary")

    if generate_clicked or f"report_data_{selected_report}" in st.session_state:
        if generate_clicked:
            try:
                if selected_report == "Email Activity Report":
                    s_str = start_date.isoformat() if start_date else None
                    e_str = end_date.isoformat() if end_date else None
                    path, count = generate_email_activity_report(
                        db_path=DEFAULT_DB_PATH,
                        start_date=s_str,
                        end_date=e_str,
                    )
                elif selected_report == "Reminder Status Count Report":
                    path, count = generate_reminder_status_report(db_path=DEFAULT_DB_PATH)
                elif selected_report == "Activity History Audit Report":
                    path, count = generate_activity_history_report(db_path=DEFAULT_DB_PATH, limit=1000)
                else:  # Reminder Details Report
                    path, count = generate_reminder_details_report(db_path=DEFAULT_DB_PATH)

                csv_bytes = path.read_text(encoding="utf-8")
                st.session_state[f"report_path_{selected_report}"] = str(path)
                st.session_state[f"report_data_{selected_report}"] = csv_bytes
                st.session_state[f"report_count_{selected_report}"] = count
            except Exception as e:
                st.error(f"Failed to generate report: {e}")
                return

        csv_content = st.session_state.get(f"report_data_{selected_report}", "")
        report_path_str = st.session_state.get(f"report_path_{selected_report}", "")
        record_count = st.session_state.get(f"report_count_{selected_report}", 0)

        if csv_content:
            st.success(f"Report generated successfully! Exported **{record_count}** records to `{Path(report_path_str).name}`.")

            # Download Button
            filename = Path(report_path_str).name if report_path_str else f"{selected_report.lower().replace(' ', '_')}.csv"
            st.download_button(
                label=f"📥 Download {filename}",
                data=csv_content,
                file_name=filename,
                mime="text/csv",
            )

            # Preview Section
            st.markdown("### 📋 Report Preview")
            from io import StringIO
            preview_df = pd.read_csv(StringIO(csv_content))
            render_dataframe(preview_df, height=350)


if __name__ == "__main__":
    from dashboard.components.theme import init_theme, apply_theme
    init_theme()
    apply_theme()
    render_reports_page()
