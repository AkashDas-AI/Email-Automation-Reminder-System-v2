"""Theme Manager Component

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Provides permanent, fixed Dark Mode styling, color palettes,
and Plotly chart template synchronization for the Streamlit dashboard.
"""

from __future__ import annotations

import streamlit as st
from typing import Dict

DARK_PALETTE: Dict[str, str] = {
    "bg": "#0E1117",
    "card_bg": "#1A1F2C",
    "card_border": "#2D3748",
    "text": "#F1F5F9",
    "text_muted": "#94A3B8",
    "primary": "#3B82F6",
    "primary_hover": "#2563EB",
    "success": "#10B981",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "info": "#0EA5E9",
    "purple": "#8B5CF6",
    "plotly_template": "plotly_dark",
}

DEFAULT_THEME = "dark"


def init_theme() -> None:
    """Initializes the fixed Dark Mode theme in Streamlit session state."""
    st.session_state["theme"] = DEFAULT_THEME


def get_current_theme() -> str:
    """Returns the single permanent active theme ('dark')."""
    return DEFAULT_THEME


def get_theme_colors() -> Dict[str, str]:
    """Returns the active Dark Mode color palette dictionary."""
    return DARK_PALETTE


def get_plotly_template() -> str:
    """Returns the Plotly template matching the permanent Dark Mode ('plotly_dark')."""
    return DARK_PALETTE["plotly_template"]


def apply_theme() -> None:
    """Injects permanent Dark Mode CSS into the Streamlit application."""
    c = get_theme_colors()

    css = f"""
    <style>
        /* Base dark mode styles */
        .stApp {{
            background-color: {c['bg']};
            color: {c['text']};
        }}
        section[data-testid="stSidebar"] {{
            background-color: #131722;
            border-right: 1px solid {c['card_border']};
        }}
        
        /* KPI Card Styles */
        .kpi-card {{
            background: linear-gradient(135deg, {c['card_bg']} 0%, #171B26 100%);
            border: 1px solid {c['card_border']};
            border-radius: 12px;
            padding: 1.2rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            margin-bottom: 0.8rem;
        }}
        .kpi-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 12px -1px rgba(0, 0, 0, 0.4);
            border-color: {c['primary']};
        }}
        .kpi-title {{
            font-size: 0.82rem;
            font-weight: 600;
            color: {c['text_muted']};
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.4rem;
        }}
        .kpi-value {{
            font-size: 2.0rem;
            font-weight: 700;
            color: {c['text']};
            line-height: 1.2;
            margin-bottom: 0.2rem;
        }}
        .kpi-subtitle {{
            font-size: 0.78rem;
            color: {c['text_muted']};
        }}
        
        /* Status Pills */
        .status-pill {{
            display: inline-block;
            padding: 0.25rem 0.6rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-align: center;
        }}
        .pill-pending {{ background: rgba(100, 116, 139, 0.2); color: #94A3B8; border: 1px solid #475569; }}
        .pill-ready {{ background: rgba(14, 165, 233, 0.2); color: #38BDF8; border: 1px solid #0284C7; }}
        .pill-processing {{ background: rgba(245, 158, 11, 0.2); color: #FBBF24; border: 1px solid #D97706; }}
        .pill-simulated {{ background: rgba(139, 92, 246, 0.2); color: #A78BFA; border: 1px solid #7C3AED; }}
        .pill-sent {{ background: rgba(16, 185, 129, 0.2); color: #34D399; border: 1px solid #059669; }}
        .pill-failed {{ background: rgba(239, 68, 68, 0.2); color: #F87171; border: 1px solid #DC2626; }}
        .pill-delivery-unknown {{ background: rgba(249, 115, 22, 0.2); color: #FB923C; border: 1px solid #EA580C; }}

        /* Section headers */
        h1, h2, h3, h4 {{
            color: {c['text']} !important;
        }}
        
        /* Footnotes & muted text */
        .author-badge {{
            color: {c['text_muted']};
            font-size: 0.85rem;
            margin-bottom: 1rem;
        }}
    </style>
    """

    st.markdown(css, unsafe_allow_html=True)
