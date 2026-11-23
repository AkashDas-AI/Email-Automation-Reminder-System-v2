"""Dashboard Charts Component

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Generates theme-aware Plotly visualizations for the Streamlit dashboard.
"""

from __future__ import annotations

from typing import Any, Dict
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from .theme import get_plotly_template, get_theme_colors

STATUS_COLOR_MAP = {
    "pending": "#64748B",
    "ready": "#0EA5E9",
    "processing": "#F59E0B",
    "simulated": "#8B5CF6",
    "sent": "#10B981",
    "failed": "#EF4444",
    "delivery_unknown": "#F97316",
    "sent (SMTP accepted)": "#10B981",
}


def plot_status_distribution(status_counts: Dict[str, int]) -> go.Figure:
    """Creates a donut chart displaying distribution across all reminder statuses."""
    template = get_plotly_template()
    c = get_theme_colors()

    # Filter out zero counts for visual clarity, unless all are zero
    filtered_items = [(k, v) for k, v in status_counts.items() if v > 0]
    if not filtered_items:
        filtered_items = [("No Data", 1)]

    labels = [k for k, _ in filtered_items]
    values = [v for _, v in filtered_items]
    colors = [STATUS_COLOR_MAP.get(k, c["primary"]) for k in labels]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                marker=dict(colors=colors, line=dict(color=c["card_bg"], width=2)),
                textinfo="label+percent",
                hoverinfo="label+value+percent",
            )
        ]
    )

    fig.update_layout(
        template=template,
        title=dict(text="Reminder Status Breakdown", font=dict(size=16)),
        margin=dict(t=40, b=20, l=20, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def plot_outcome_breakdown(kpis: Dict[str, Any]) -> go.Figure:
    """Creates a bar chart comparing Simulated, Sent, Failed, and Delivery Unknown."""
    template = get_plotly_template()
    c = get_theme_colors()

    categories = ["Simulated", "Sent (SMTP)", "Failed", "Delivery Unknown"]
    counts = [
        kpis.get("simulated", 0),
        kpis.get("smtp_accepted", 0),
        kpis.get("failed", 0),
        kpis.get("delivery_unknown", 0),
    ]
    colors = [STATUS_COLOR_MAP["simulated"], STATUS_COLOR_MAP["sent"], STATUS_COLOR_MAP["failed"], STATUS_COLOR_MAP["delivery_unknown"]]

    fig = go.Figure(
        data=[
            go.Bar(
                x=categories,
                y=counts,
                marker=dict(color=colors, cornerradius=6),
                text=counts,
                textposition="auto",
            )
        ]
    )

    fig.update_layout(
        template=template,
        title=dict(text="Dispatch Outcomes Comparison", font=dict(size=16)),
        xaxis=dict(title="Outcome Category"),
        yaxis=dict(title="Reminder Count", rangemode="tozero"),
        margin=dict(t=40, b=30, l=30, r=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def plot_department_distribution(dept_counts: Dict[str, int]) -> go.Figure:
    """Creates a horizontal bar chart of reminders by recipient department."""
    template = get_plotly_template()
    c = get_theme_colors()

    if not dept_counts:
        dept_counts = {"Unassigned": 0}

    depts = list(dept_counts.keys())
    counts = list(dept_counts.values())

    # Sort ascending for horizontal bar chart
    sorted_pairs = sorted(zip(depts, counts), key=lambda x: x[1])
    depts = [p[0] for p in sorted_pairs]
    counts = [p[1] for p in sorted_pairs]

    fig = go.Figure(
        data=[
            go.Bar(
                x=counts,
                y=depts,
                orientation="h",
                marker=dict(color=c["primary"], cornerradius=4),
                text=counts,
                textposition="auto",
            )
        ]
    )

    fig.update_layout(
        template=template,
        title=dict(text="Reminders by Department", font=dict(size=16)),
        xaxis=dict(title="Reminders", rangemode="tozero"),
        yaxis=dict(title="Department"),
        margin=dict(t=40, b=30, l=40, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def plot_template_distribution(template_counts: Dict[str, int]) -> go.Figure:
    """Creates a bar chart of reminders by template key."""
    template = get_plotly_template()
    c = get_theme_colors()

    if not template_counts:
        template_counts = {"None": 0}

    templates = list(template_counts.keys())
    counts = list(template_counts.values())

    fig = go.Figure(
        data=[
            go.Bar(
                x=templates,
                y=counts,
                marker=dict(color=c["info"], cornerradius=6),
                text=counts,
                textposition="auto",
            )
        ]
    )

    fig.update_layout(
        template=template,
        title=dict(text="Reminders by Template Key", font=dict(size=16)),
        xaxis=dict(title="Template Key"),
        yaxis=dict(title="Reminders", rangemode="tozero"),
        margin=dict(t=40, b=30, l=30, r=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def plot_activity_timeline(df: pd.DataFrame) -> go.Figure:
    """Creates a chart visualizing activity log frequency grouped by event type."""
    template = get_plotly_template()
    c = get_theme_colors()

    if df.empty or "Event Type" not in df.columns:
        fig = go.Figure()
        fig.update_layout(
            template=template,
            title=dict(text="Recent Activity Log (No Events Found)", font=dict(size=16)),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    event_counts = df["Event Type"].value_counts().reset_index()
    event_counts.columns = ["Event Type", "Count"]

    fig = go.Figure(
        data=[
            go.Bar(
                x=event_counts["Event Type"],
                y=event_counts["Count"],
                marker=dict(color=c["purple"], cornerradius=6),
                text=event_counts["Count"],
                textposition="auto",
            )
        ]
    )

    fig.update_layout(
        template=template,
        title=dict(text="Recent Audit Events by Type", font=dict(size=16)),
        xaxis=dict(title="Event Type", tickangle=-25),
        yaxis=dict(title="Log Count", rangemode="tozero"),
        margin=dict(t=40, b=60, l=30, r=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def plot_company_distribution(company_counts: Dict[str, int]) -> go.Figure:
    """Creates a horizontal bar chart of reminders grouped by recipient company."""
    template = get_plotly_template()
    c = get_theme_colors()

    if not company_counts:
        company_counts = {"Unassigned": 0}

    sorted_pairs = sorted(company_counts.items(), key=lambda x: x[1])
    companies = [p[0] for p in sorted_pairs]
    counts = [p[1] for p in sorted_pairs]

    fig = go.Figure(
        data=[
            go.Bar(
                x=counts,
                y=companies,
                orientation="h",
                marker=dict(color="#14B8A6", cornerradius=4),
                text=counts,
                textposition="auto",
            )
        ]
    )

    fig.update_layout(
        template=template,
        title=dict(text="Reminders by Company", font=dict(size=16)),
        xaxis=dict(title="Reminders", rangemode="tozero"),
        yaxis=dict(title="Company"),
        margin=dict(t=40, b=30, l=60, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def plot_category_distribution(category_counts: Dict[str, int]) -> go.Figure:
    """Creates a bar chart of reminders by functional category (reminder_type)."""
    template = get_plotly_template()
    c = get_theme_colors()

    if not category_counts:
        category_counts = {"Unclassified": 0}

    labels = [k.title() for k in category_counts.keys()]
    counts = list(category_counts.values())

    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=counts,
                marker=dict(color=c["primary"], cornerradius=6),
                text=counts,
                textposition="auto",
            )
        ]
    )

    fig.update_layout(
        template=template,
        title=dict(text="Reminders by Category", font=dict(size=16)),
        xaxis=dict(title="Category"),
        yaxis=dict(title="Reminders", rangemode="tozero"),
        margin=dict(t=40, b=30, l=30, r=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def plot_lead_time_distribution(lead_buckets: Dict[str, int]) -> go.Figure:
    """Creates a bar chart showing upcoming workload across lead-time horizons."""
    template = get_plotly_template()
    c = get_theme_colors()

    labels = ["Next 24h", "Next 7 Days", "Next 30 Days", "Beyond 30 Days"]
    counts = [
        lead_buckets.get("due_next_24h", 0),
        lead_buckets.get("due_next_7d", 0),
        lead_buckets.get("due_next_30d", 0),
        lead_buckets.get("due_beyond_30d", 0),
    ]

    colors = [c["danger"], c["warning"], c["info"], c["primary"]]

    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=counts,
                marker=dict(color=colors, cornerradius=6),
                text=counts,
                textposition="auto",
            )
        ]
    )

    fig.update_layout(
        template=template,
        title=dict(text="Upcoming Workload Lead-Time Horizon", font=dict(size=16)),
        xaxis=dict(title="Lead Time Horizon"),
        yaxis=dict(title="Reminders", rangemode="tozero"),
        margin=dict(t=40, b=30, l=30, r=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def plot_temporal_due_distribution(by_day: Dict[str, int]) -> go.Figure:
    """Creates a chronological bar chart showing reminder due dates."""
    template = get_plotly_template()
    c = get_theme_colors()

    if not by_day:
        fig = go.Figure()
        fig.update_layout(
            template=template,
            title=dict(text="Reminder Due Date Timeline (No Data)", font=dict(size=16)),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        return fig

    dates = list(by_day.keys())
    counts = list(by_day.values())

    fig = go.Figure(
        data=[
            go.Bar(
                x=dates,
                y=counts,
                marker=dict(color=c["purple"], cornerradius=4),
                text=counts,
                textposition="auto",
            )
        ]
    )

    fig.update_layout(
        template=template,
        title=dict(text="Reminder Schedule Timeline (Due Dates)", font=dict(size=16)),
        xaxis=dict(title="Due Date", tickangle=-45),
        yaxis=dict(title="Reminders Due", rangemode="tozero"),
        margin=dict(t=40, b=70, l=30, r=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def plot_overdue_vs_upcoming(overdue_count: int, upcoming_count: int) -> go.Figure:
    """Creates a donut chart comparing Overdue vs Upcoming reminder volume."""
    template = get_plotly_template()
    c = get_theme_colors()

    total = overdue_count + upcoming_count
    if total == 0:
        labels = ["No Reminders"]
        values = [1]
        colors = [c["text_muted"]]
    else:
        labels = ["Overdue", "Upcoming"]
        values = [overdue_count, upcoming_count]
        colors = [c["danger"], c["success"]]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.6,
                marker=dict(colors=colors, line=dict(color=c["card_bg"], width=2)),
                textinfo="label+percent" if total > 0 else "label",
                hoverinfo="label+value+percent" if total > 0 else "label",
            )
        ]
    )

    fig.update_layout(
        template=template,
        title=dict(text="Schedule Status Balance", font=dict(size=16)),
        margin=dict(t=40, b=20, l=20, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig

