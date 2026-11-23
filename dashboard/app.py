"""Streamlit Dashboard Entry Point

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Main multi-page navigation interface connecting to shared application services.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from dashboard.components.theme import init_theme, apply_theme
from dashboard.pages.overview import render_overview_page
from dashboard.pages.contacts import render_contacts_page
from dashboard.pages.reminders import render_reminders_page
from dashboard.pages.email_history import render_email_history_page
from dashboard.pages.insights import render_insights_page
from dashboard.pages.reports import render_reports_page
from dashboard.pages.settings import render_settings_page


def main() -> None:
    """Main application bootstrap and navigation router."""
    st.set_page_config(
        page_title="Email Automation & Reminder System",
        page_icon="📬",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Initialize and apply permanent Dark Mode theme
    init_theme()
    apply_theme()

    # Sidebar Header
    st.sidebar.markdown("## 📬 Email Automation")
    st.sidebar.markdown(
        '<div style="font-size: 0.85rem; color: #94A3B8; margin-top: -0.5rem; margin-bottom: 0.8rem;">'
        'Author: <strong>Akash Das</strong></div>',
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("---")

    # Navigation Menu
    nav_options = [
        "🏠 Overview",
        "👥 Contacts",
        "⏰ Reminders",
        "📨 Email History",
        "📊 Insights & Analytics",
        "📑 Reports",
        "⚙️ Settings & Diagnostics",
    ]

    default_nav_idx = 0
    try:
        page_param = st.query_params.get("page")
        if page_param:
            for i, opt in enumerate(nav_options):
                if page_param.lower() in opt.lower():
                    default_nav_idx = i
                    break
    except Exception:
        pass

    selected_nav = st.sidebar.radio(
        "Navigation",
        options=nav_options,
        index=default_nav_idx,
        label_visibility="collapsed",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        '<div style="font-size: 0.75rem; color: #64748B; text-align: center;">'
        'Phase 10 — Streamlit Dashboard<br>'
        'Email Automation & Reminder System<br>'
        '<strong>Akash Das</strong>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Route to selected page
    if selected_nav == "🏠 Overview":
        render_overview_page()
    elif selected_nav == "👥 Contacts":
        render_contacts_page()
    elif selected_nav == "⏰ Reminders":
        render_reminders_page()
    elif selected_nav == "📨 Email History":
        render_email_history_page()
    elif selected_nav == "📊 Insights & Analytics":
        render_insights_page()
    elif selected_nav == "📑 Reports":
        render_reports_page()
    elif selected_nav == "⚙️ Settings & Diagnostics":
        render_settings_page()


if __name__ == "__main__":
    main()
