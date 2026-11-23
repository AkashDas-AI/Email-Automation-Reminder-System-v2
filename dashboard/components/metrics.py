"""Dashboard Metric Cards Component

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Reusable KPI metric card rendering helpers for Streamlit.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import streamlit as st

from .theme import get_theme_colors


def render_kpi_card(
    title: str,
    value: Any,
    subtitle: Optional[str] = None,
    icon: Optional[str] = None,
    color: Optional[str] = None,
) -> None:
    """Renders a styled KPI metric card using permanent Dark Mode styling."""
    c = get_theme_colors()
    card_color = color or c["primary"]
    icon_str = f"{icon} " if icon else ""
    sub_str = f'<div class="kpi-subtitle">{subtitle}</div>' if subtitle else ""

    html = f"""
    <div class="kpi-card" style="border-left: 4px solid {card_color};">
        <div class="kpi-title">{icon_str}{title}</div>
        <div class="kpi-value">{value}</div>
        {sub_str}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_kpi_grid(kpis: Dict[str, Any]) -> None:
    """Renders the comprehensive 8-metric KPI grid on the dashboard.
    
    Formula Invariants:
        - Attempted = Simulated + SMTP Accepted (Sent) + Failed
        - Pending, ready, and processing are strictly excluded from attempted.
        - Delivery unknown is excluded from success rate denominator.
        - Success rate = (Simulated + Sent) / Attempted * 100%
    """
    c = get_theme_colors()

    # Row 1: Core System & Dispatch Volume
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        render_kpi_card(
            title="Total Contacts",
            value=f"{kpis.get('total_contacts', 0):,}",
            subtitle="Registered contact records",
            icon="👥",
            color=c["primary"],
        )
    with col2:
        render_kpi_card(
            title="Total Reminders",
            value=f"{kpis.get('total_reminders', 0):,}",
            subtitle="All scheduled reminders",
            icon="⏰",
            color=c["info"],
        )
    with col3:
        render_kpi_card(
            title="Attempted Dispatches",
            value=f"{kpis.get('attempted', 0):,}",
            subtitle="Simulated + Sent + Failed",
            icon="🚀",
            color=c["purple"],
        )
    with col4:
        rate = kpis.get("success_rate", 0.0)
        rate_color = c["success"] if rate >= 80.0 else (c["warning"] if rate >= 50.0 else c["danger"])
        render_kpi_card(
            title="Dispatch Success Rate",
            value=f"{rate:.1f}%",
            subtitle="Excludes pipeline & unknown",
            icon="🎯",
            color=rate_color,
        )

    # Row 2: Dispatch Outcomes & Queue State
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        render_kpi_card(
            title="Simulated (Dry-Run)",
            value=f"{kpis.get('simulated', 0):,}",
            subtitle="Validated sandbox dispatch",
            icon="🧪",
            color=c["purple"],
        )
    with col6:
        render_kpi_card(
            title="Sent (SMTP Accepted)",
            value=f"{kpis.get('smtp_accepted', 0):,}",
            subtitle="Relayed by smtp.gmail.com",
            icon="✉️",
            color=c["success"],
        )
    with col7:
        render_kpi_card(
            title="Failed Dispatches",
            value=f"{kpis.get('failed', 0):,}",
            subtitle="Terminal dispatch errors",
            icon="⚠️",
            color=c["danger"],
        )
    with col8:
        pending = kpis.get("pending", 0)
        ready = kpis.get("ready", 0)
        delivery_unknown = kpis.get("delivery_unknown", 0)
        sub_text = f"Pending: {pending} | Ready: {ready} | Unknown: {delivery_unknown}"
        render_kpi_card(
            title="Pipeline & Unknown",
            value=f"{pending + ready + delivery_unknown:,}",
            subtitle=sub_text,
            icon="⏳",
            color=c["warning"],
        )
