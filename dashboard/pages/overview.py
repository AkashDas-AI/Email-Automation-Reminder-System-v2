"""Dashboard Overview Page

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Displays system health, primary KPI cards, status charts, and recent activity.
"""

from __future__ import annotations

import streamlit as st

from src.email_automation.config import load_config
from src.email_automation.database import DEFAULT_DB_PATH
from src.email_automation.insights import get_system_kpis, get_activity_timeline_df
from dashboard.components.metrics import render_kpi_grid
from dashboard.components.charts import plot_status_distribution, plot_outcome_breakdown
from dashboard.components.tables import render_dataframe
from dashboard.components.theme import get_theme_colors


def render_overview_page() -> None:
    """Renders the main system overview page."""
    c = get_theme_colors()
    config = load_config()
    kpis = get_system_kpis(DEFAULT_DB_PATH)

    # Page Header
    st.markdown("## 📊 System Operational Overview")
    st.markdown(
        '<div class="author-badge">Author: <strong>Akash Das</strong> | Email Automation & Reminder System</div>',
        unsafe_allow_html=True,
    )

    # Operational Health & Environment Status Banner
    mode_badge = "🧪 DRY-RUN (Simulation Active)" if config.dry_run else "⚡ LIVE SMTP DISPATCH"
    mode_color = c["purple"] if config.dry_run else c["danger"]
    
    col_stat1, col_stat2, col_stat3 = st.columns([2, 1, 1])
    with col_stat1:
        st.markdown(
            f"""
            <div style="padding: 0.6rem 1rem; border-radius: 8px; background: {c['card_bg']}; border: 1px solid {c['card_border']}; margin-bottom: 1rem;">
                <strong>Dispatch Mode:</strong> <span style="color: {mode_color}; font-weight: bold;">{mode_badge}</span>
                <span style="color: {c['text_muted']}; margin-left: 1rem;">| Relay: smtp.gmail.com:587 (STARTTLS)</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_stat2:
        st.markdown(
            f"""
            <div style="padding: 0.6rem 1rem; border-radius: 8px; background: {c['card_bg']}; border: 1px solid {c['card_border']}; margin-bottom: 1rem;">
                <strong>Database:</strong> <span style="color: {c['success']}; font-weight: bold;">Connected (v9)</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_stat3:
        st.markdown(
            f"""
            <div style="padding: 0.6rem 1rem; border-radius: 8px; background: {c['card_bg']}; border: 1px solid {c['card_border']}; margin-bottom: 1rem;">
                <strong>Scheduler:</strong> <span style="color: {c['info']}; font-weight: bold;">Ready</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Primary 8 KPI Cards Grid
    render_kpi_grid(kpis)

    st.markdown("---")

    # Visualizations Row
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        fig_status = plot_status_distribution(kpis["status_counts"])
        st.plotly_chart(fig_status, use_container_width=True)

    with col_chart2:
        fig_outcome = plot_outcome_breakdown(kpis)
        st.plotly_chart(fig_outcome, use_container_width=True)

    st.markdown("---")

    # Recent Activity Feed
    st.markdown("### 🕒 Recent System Activity History")
    timeline_df = get_activity_timeline_df(DEFAULT_DB_PATH, limit=10)
    render_dataframe(timeline_df)


if __name__ == "__main__":
    from dashboard.components.theme import init_theme, apply_theme
    init_theme()
    apply_theme()
    render_overview_page()
