"""Dashboard Table Helper Component

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Reusable styled dataframe and table rendering helpers.
"""

from __future__ import annotations

from typing import Any, Optional, Union
import pandas as pd
import streamlit as st


def _sanitize_height(height: Optional[Union[int, str]]) -> Optional[Union[int, str]]:
    """Sanitizes height to ensure compatibility with Streamlit's height contract.

    Valid Streamlit values:
    - Positive integers (pixels, e.g. 350, 380)
    - Valid string literals: 'auto', 'content', 'stretch'
    - Any invalid, negative, non-positive, or None value returns None (omitted).
    """
    if height is None:
        return None
    if isinstance(height, int) and not isinstance(height, bool):
        return height if height > 0 else None
    if isinstance(height, str):
        clean_str = height.strip().lower()
        if clean_str in {"auto", "content", "stretch"}:
            return clean_str
        if clean_str.isdigit() and int(clean_str) > 0:
            return int(clean_str)
        return None
    return None


def render_dataframe(
    df: pd.DataFrame,
    use_container_width: bool = True,
    hide_index: bool = True,
    height: Optional[Union[int, str]] = None,
    column_config: Optional[dict[str, Any]] = None,
    column_order: Optional[list[str]] = None,
    **kwargs: Any,
) -> None:
    """Renders a formatted pandas DataFrame inside Streamlit with responsive styling.

    Never passes height=None to st.dataframe(), preventing StreamlitInvalidHeightError.
    If height is None or invalid, the height parameter is completely omitted so
    Streamlit applies its default responsive sizing ('auto').
    """
    if df is None or df.empty:
        st.info("No matching records found.")
        return

    st_kwargs: dict[str, Any] = {
        "use_container_width": use_container_width,
        "hide_index": hide_index,
    }

    if column_config is not None:
        st_kwargs["column_config"] = column_config
    if column_order is not None:
        st_kwargs["column_order"] = column_order

    sanitized_height = _sanitize_height(height)
    if sanitized_height is not None:
        st_kwargs["height"] = sanitized_height

    # Safely merge any additional keyword arguments
    for k, v in kwargs.items():
        if k == "height":
            sanitized_v = _sanitize_height(v)
            if sanitized_v is not None:
                st_kwargs["height"] = sanitized_v
            else:
                st_kwargs.pop("height", None)
        elif v is not None:
            st_kwargs[k] = v

    st.dataframe(df, **st_kwargs)


def render_table(df: pd.DataFrame) -> None:
    """Renders a static table using st.table with safety checks."""
    if df is None or df.empty:
        st.info("No matching records found.")
        return
    st.table(df)
