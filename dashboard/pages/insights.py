"""Dashboard Insights & Analytics Page

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Comprehensive operational intelligence, multi-dimensional analytics,
and automated interpretation engine grounded in actual database records.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from src.email_automation.config import load_config
from src.email_automation.database import DEFAULT_DB_PATH
from src.email_automation.insights import (
    get_system_kpis,
    get_reminder_status_metrics,
    get_dispatch_performance_metrics,
    get_time_distribution_metrics,
    get_department_and_company_metrics,
    get_category_and_template_metrics,
    get_operational_workload_metrics,
    generate_system_interpretations,
    get_activity_timeline_df,
)
from dashboard.components.charts import (
    plot_status_distribution,
    plot_outcome_breakdown,
    plot_department_distribution,
    plot_template_distribution,
    plot_activity_timeline,
    plot_company_distribution,
    plot_category_distribution,
    plot_lead_time_distribution,
    plot_temporal_due_distribution,
    plot_overdue_vs_upcoming,
)
from dashboard.components.tables import render_dataframe
from dashboard.components.theme import get_theme_colors


def render_insights_page() -> None:
    """Renders the comprehensive Phase 11 visual analytics and interpretation page."""
    c = get_theme_colors()
    config = load_config()

    # Load all analytical metrics from SQLite
    kpis = get_system_kpis(DEFAULT_DB_PATH)
    status_m = get_reminder_status_metrics(DEFAULT_DB_PATH)
    perf_m = get_dispatch_performance_metrics(DEFAULT_DB_PATH)
    dept_m = get_department_and_company_metrics(DEFAULT_DB_PATH)
    cat_m = get_category_and_template_metrics(DEFAULT_DB_PATH)
    time_m = get_time_distribution_metrics(DEFAULT_DB_PATH)
    op_m = get_operational_workload_metrics(DEFAULT_DB_PATH)
    interpretations = generate_system_interpretations(DEFAULT_DB_PATH)

    # 1. Page Header & Author Citation
    st.markdown("## 📊 System Insights & Operational Interpretation")
    st.markdown(
        '<div class="author-badge">Author: <strong>Akash Das</strong> | Phase 11 Advanced Analytics & Interpretation Engine</div>',
        unsafe_allow_html=True,
    )

    # 2. Executive Operational KPI Ribbon
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    with m_col1:
        st.metric(
            label="Total Workload",
            value=f"{status_m['total_reminders']} Reminders",
            delta=f"{status_m['upcoming_count']} Upcoming ({status_m['upcoming_pct']}%)",
            delta_color="normal",
        )
    with m_col2:
        st.metric(
            label="Schedule Health",
            value=f"{status_m['overdue_count']} Overdue",
            delta="Actionable Due" if status_m['overdue_count'] > 0 else "All On Schedule",
            delta_color="inverse" if status_m['overdue_count'] > 0 else "normal",
        )
    with m_col3:
        if perf_m["has_attempted"]:
            st.metric(
                label="Dispatch Success Rate",
                value=f"{perf_m['success_rate']:.1f}%",
                delta=f"{perf_m['attempted']} Dispatches Attempted",
            )
        else:
            st.metric(
                label="Dispatch Success Rate",
                value="N/A (0 Attempts)",
                delta="Pending Scheduled Dates",
                delta_color="off",
            )
    with m_col4:
        st.metric(
            label="Operational Review Alerts",
            value=f"{perf_m['delivery_unknown']} Unknown",
            delta="Review Required" if perf_m['delivery_unknown'] > 0 else "Zero Ambiguity",
            delta_color="inverse" if perf_m['delivery_unknown'] > 0 else "normal",
        )

    st.markdown("---")

    # 3. Phase 11 Automated Interpretation Engine Section
    st.markdown("### 🧠 Operational Interpretation Engine")
    st.caption("Factual, data-grounded operational interpretations generated directly from verified records. Zero synthetic assumptions.")

    border_subtle = c.get("card_border", "#2D3748")
    accent_color = c.get("info", "#0EA5E9")

    for item in interpretations:
        border_color = (
            c["success"] if item["severity"] == "success"
            else (c["warning"] if item["severity"] == "warning"
            else (c["danger"] if item["severity"] == "error"
            else c["info"]))
        )
        st.markdown(
            f"""
            <div style="background-color: {c['card_bg']}; border-left: 4px solid {border_color}; border-radius: 6px; padding: 14px 18px; margin-bottom: 12px; border-top: 1px solid {border_subtle}; border-right: 1px solid {border_subtle}; border-bottom: 1px solid {border_subtle};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-weight: 600; font-size: 1.0rem; color: {c['text']};">{item['title']}</span>
                    <span style="background-color: {border_subtle}; color: {c['text_muted']}; padding: 2px 8px; border-radius: 12px; font-size: 0.8rem; font-weight: 500;">{item['badge']}</span>
                </div>
                <div style="font-size: 0.92rem; color: {c['text']}; line-height: 1.5; margin-bottom: 6px;">{item['finding']}</div>
                <div style="font-size: 0.8rem; color: {c['text_muted']}; font-family: monospace;">{item['evidence']}</div>
                <div style="font-size: 0.82rem; color: {accent_color}; margin-top: 6px;">💡 <em>Recommendation: {item['actionable']}</em></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # 4. Multi-Dimensional Analytical Views (Tabs)
    tab_dept, tab_cat, tab_time, tab_perf, tab_audit = st.tabs([
        "👥 Department & Company",
        "🏷️ Categories & Templates",
        "📅 Schedule & Lead Times",
        "📨 Dispatch Reliability",
        "🕒 Audit Timeline",
    ])

    with tab_dept:
        st.markdown("#### 🏢 Department & Company Workload Concentration")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.plotly_chart(plot_department_distribution(dept_m["department_counts"]), use_container_width=True)
        with col_d2:
            st.plotly_chart(plot_company_distribution(dept_m["company_counts"]), use_container_width=True)

        if dept_m["sample_size_caveat"]:
            st.info(f"ℹ️ {dept_m['sample_size_caveat']}")

        # Detailed breakdown table
        dept_rows = []
        for d, cnt in dept_m["department_counts"].items():
            pct = round((cnt / dept_m["total_reminders"] * 100.0), 1) if dept_m["total_reminders"] > 0 else 0.0
            dept_rows.append({"Department": d, "Reminders": cnt, "Share (%)": f"{pct}%"})
        render_dataframe(pd.DataFrame(dept_rows))

    with tab_cat:
        st.markdown("#### 🏷️ Reminder Categories and Functional Templates")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.plotly_chart(plot_category_distribution(cat_m["category_counts"]), use_container_width=True)
        with col_c2:
            st.plotly_chart(plot_template_distribution(cat_m["template_counts"]), use_container_width=True)

        cat_rows = []
        for cat, cnt in cat_m["category_counts"].items():
            pct = round((cnt / cat_m["total_reminders"] * 100.0), 1) if cat_m["total_reminders"] > 0 else 0.0
            cat_rows.append({"Category": cat.title(), "Reminders": cnt, "Share (%)": f"{pct}%"})
        render_dataframe(pd.DataFrame(cat_rows))

    with tab_time:
        st.markdown("#### 📅 Temporal Distribution and Upcoming Lead Times")
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.plotly_chart(plot_overdue_vs_upcoming(status_m["overdue_count"], status_m["upcoming_count"]), use_container_width=True)
        with col_t2:
            st.plotly_chart(plot_lead_time_distribution(time_m["lead_time_buckets"]), use_container_width=True)

        st.plotly_chart(plot_temporal_due_distribution(time_m["by_day"]), use_container_width=True)

        if status_m["overdue_count"] == 0:
            st.success("✅ Zero reminders are overdue relative to current UTC time. All 24 reminders are scheduled for future dates.")
        else:
            st.warning(f"⚠️ {status_m['overdue_count']} reminders are past due date and awaiting dispatch preparation.")

    with tab_perf:
        st.markdown("#### 📨 Email Dispatch Execution & Handover Reliability")
        st.plotly_chart(plot_outcome_breakdown(kpis), use_container_width=True)

        if not perf_m["has_attempted"]:
            st.info(
                "ℹ️ **No dispatches attempted yet.** The current dataset consists of future-dated reminders in `pending` status. "
                "The email dispatch success rate formula will be calculated once dispatches are simulated or executed via SMTP. "
                "Zero dispatches is an accurate operational reflection of future scheduling, not a system failure."
            )
        else:
            st.caption(f"Operational Success Rate: **{perf_m['formatted_success_rate']}** ({perf_m['attempted']} attempts).")

        st.markdown(f"*{perf_m['smtp_delivery_clarification']}*")

        # Mathematical Standards Table
        st.markdown("---")
        st.markdown("##### 📐 Calculation Standards & Definitions")
        kpi_summary_data = {
            "Metric Classification": [
                "Total Contacts",
                "Total Reminders",
                "Pipeline: Pending",
                "Pipeline: Ready",
                "Pipeline: Processing",
                "Outcome: Simulated (Dry-Run)",
                "Outcome: Sent (SMTP Accepted)",
                "Outcome: Failed (Terminal)",
                "Ambiguous: Delivery Unknown",
                "Calculated Attempted Dispatches",
                "Operational Success Rate (%)",
            ],
            "Count / Value": [
                kpis["total_contacts"],
                kpis["total_reminders"],
                kpis["pending"],
                kpis["ready"],
                kpis["processing"],
                kpis["simulated"],
                kpis["smtp_accepted"],
                kpis["failed"],
                kpis["delivery_unknown"],
                kpis["attempted"],
                perf_m["formatted_success_rate"],
            ],
            "Role in Statistics": [
                "System Entity Total",
                "System Entity Total",
                "Queued for Scheduling (Excluded from Attempted)",
                "Personalized & Waiting Dispatch (Excluded from Attempted)",
                "Actively In Flight (Excluded from Attempted)",
                "Successful Sandbox Delivery (Numerator & Denominator)",
                "Accepted by smtp.gmail.com (Numerator & Denominator)",
                "Failed Delivery (Denominator only)",
                "Ambiguous Relaying (Isolated Operational Alert)",
                "Simulated + Sent + Failed",
                "((Simulated + Sent) / Attempted) * 100",
            ],
        }
        render_dataframe(pd.DataFrame(kpi_summary_data))

    with tab_audit:
        st.markdown("#### 🕒 Audit Activity Event Frequency & Timeline")
        timeline_df = get_activity_timeline_df(DEFAULT_DB_PATH, limit=100)
        st.plotly_chart(plot_activity_timeline(timeline_df), use_container_width=True)
        st.markdown("##### Recent Audit Log Entries")
        render_dataframe(timeline_df)


if __name__ == "__main__":
    from dashboard.components.theme import init_theme, apply_theme
    init_theme()
    apply_theme()
    render_insights_page()
