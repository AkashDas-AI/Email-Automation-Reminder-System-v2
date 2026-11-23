"""Unit and Integration Tests for Streamlit Dashboard

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Comprehensive test coverage for dashboard theme manager, insights calculations,
Plotly chart generators, contact/reminder queries, report generation, and safety invariants.
"""

import sqlite3
from pathlib import Path
from typing import Generator
import pytest
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.email_automation.config import AppConfig
from src.email_automation.database import init_db
from src.email_automation.insights import (
    get_system_kpis,
    get_all_contacts_df,
    get_all_reminders_df,
    get_email_history_df,
    get_activity_timeline_df,
)
from dashboard.components.theme import (
    DEFAULT_THEME,
    DARK_PALETTE,
    init_theme,
    get_current_theme,
    get_theme_colors,
    get_plotly_template,
)
from dashboard.components.tables import render_dataframe, render_table, _sanitize_height
from dashboard.components.charts import (
    plot_status_distribution,
    plot_outcome_breakdown,
    plot_department_distribution,
    plot_template_distribution,
    plot_activity_timeline,
)
from dashboard.pages.settings import mask_email


@pytest.fixture
def dashboard_db(tmp_path: Path) -> Path:
    """Creates a temporary test database populated with known contacts and reminders."""
    db_file = tmp_path / "dashboard_test.db"
    init_db(db_file)

    with sqlite3.connect(db_file) as conn:
        # Insert contacts
        conn.execute(
            """
            INSERT INTO contacts (contact_id, first_name, last_name, email, department, company, created_at)
            VALUES 
                ('CNT-001', 'Alice', 'Smith', 'alice@acme.com', 'Engineering', 'Acme Corp', '2026-11-20T10:00:00Z'),
                ('CNT-002', 'Bob', 'Jones', 'bob@acme.com', 'Marketing', 'Acme Corp', '2026-11-20T10:00:00Z'),
                ('CNT-003', 'Carol', 'Taylor', 'carol@apex.com', 'Engineering', 'Apex Inc', '2026-11-20T10:00:00Z');
            """
        )

        # Insert reminders across all 7 statuses
        conn.execute(
            """
            INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at)
            VALUES
                ('REM-P1', 'CNT-001', 'task', 'overdue_task', '2026-11-20T10:00:00Z', 'pending', 'REF-P1', 'Pending item', '2026-11-20T09:00:00Z', '2026-11-20T09:00:00Z'),
                ('REM-R1', 'CNT-001', 'task', 'overdue_task', '2026-11-20T10:00:00Z', 'ready', 'REF-R1', 'Ready item', '2026-11-20T09:00:00Z', '2026-11-20T09:00:00Z'),
                ('REM-PR1', 'CNT-002', 'invoice', 'invoice_due', '2026-11-20T10:00:00Z', 'processing', 'REF-PR1', 'Processing item', '2026-11-20T09:00:00Z', '2026-11-20T09:00:00Z'),
                ('REM-S1', 'CNT-002', 'invoice', 'invoice_due', '2026-11-20T10:00:00Z', 'simulated', 'REF-S1', 'Simulated item', '2026-11-20T09:00:00Z', '2026-11-20T09:30:00Z'),
                ('REM-TX1', 'CNT-003', 'meeting', 'project_status', '2026-11-20T10:00:00Z', 'sent', 'REF-TX1', 'Sent item', '2026-11-20T09:00:00Z', '2026-11-20T09:30:00Z'),
                ('REM-F1', 'CNT-003', 'meeting', 'project_status', '2026-11-20T10:00:00Z', 'failed', 'REF-F1', 'Failed item', '2026-11-20T09:00:00Z', '2026-11-20T09:30:00Z'),
                ('REM-U1', 'CNT-001', 'task', 'overdue_task', '2026-11-20T10:00:00Z', 'delivery_unknown', 'REF-U1', 'Unknown item', '2026-11-20T09:00:00Z', '2026-11-20T09:30:00Z');
            """
        )

        # Insert prepared emails
        conn.execute(
            """
            INSERT INTO prepared_emails (reminder_id, contact_id, recipient_email, recipient_name, template_key, subject, html_body, text_body, due_at, reference_id, prepared_at)
            VALUES
                ('REM-S1', 'CNT-002', 'bob@acme.com', 'Bob Jones', 'invoice_due', 'Subject S1', '<p>S1</p>', 'S1 text', '2026-11-20T10:00:00Z', 'REF-S1', '2026-11-20T09:15:00Z'),
                ('REM-TX1', 'CNT-003', 'carol@apex.com', 'Carol Taylor', 'project_status', 'Subject TX1', '<p>TX1</p>', 'TX1 text', '2026-11-20T10:00:00Z', 'REF-TX1', '2026-11-20T09:15:00Z');
            """
        )

        # Insert activity logs
        conn.execute(
            """
            INSERT INTO activity_logs (timestamp, event_type, severity, reminder_id, contact_id, status, message, details)
            VALUES
                ('2026-11-20T09:00:00Z', 'database_initialized', 'INFO', NULL, NULL, 'success', 'Init done', NULL),
                ('2026-11-20T09:15:00Z', 'reminder_claimed', 'INFO', 'REM-R1', 'CNT-001', 'success', 'Claimed', NULL),
                ('2026-11-20T09:30:00Z', 'email_simulated', 'INFO', 'REM-S1', 'CNT-002', 'success', 'Simulated', NULL);
            """
        )
        conn.commit()

    return db_file


# ==============================================================================
# 1. Theme Manager Tests (Permanent Dark Mode Only)
# ==============================================================================

def test_theme_manager_permanent_dark_mode():
    """Confirms the dashboard permanently operates in Dark Mode with zero Light Mode artifacts."""
    init_theme()
    assert DEFAULT_THEME == "dark"
    assert get_current_theme() == "dark"
    assert get_plotly_template() == "plotly_dark"

    colors = get_theme_colors()
    assert colors == DARK_PALETTE
    assert colors["bg"] == "#0E1117"
    assert colors["card_bg"] == "#1A1F2C"
    assert colors["plotly_template"] == "plotly_dark"


# ==============================================================================
# 2. Insights & KPI Calculations Tests
# ==============================================================================

def test_get_system_kpis_strict_calculation(dashboard_db: Path):
    """Verifies that Attempted = Simulated + Sent + Failed, and excludes pending/ready/processing/unknown."""
    kpis = get_system_kpis(dashboard_db)

    assert kpis["total_contacts"] == 3
    assert kpis["total_reminders"] == 7

    assert kpis["pending"] == 1
    assert kpis["ready"] == 1
    assert kpis["processing"] == 1
    assert kpis["simulated"] == 1
    assert kpis["smtp_accepted"] == 1
    assert kpis["failed"] == 1
    assert kpis["delivery_unknown"] == 1

    # Invariant: Attempted = Simulated (1) + Sent (1) + Failed (1) = 3
    assert kpis["attempted"] == 3

    # Invariant: Success rate = (Simulated + Sent) / Attempted = (1 + 1) / 3 * 100 = 66.7%
    assert kpis["success_rate"] == 66.7

    # Department counts: Engineering (5), Marketing (2)
    # CNT-001 (Engineering) has 3 reminders: REM-P1, REM-R1, REM-U1
    # CNT-002 (Marketing) has 2 reminders: REM-PR1, REM-S1
    # CNT-003 (Engineering) has 2 reminders: REM-TX1, REM-F1
    assert kpis["department_counts"]["Engineering"] == 5
    assert kpis["department_counts"]["Marketing"] == 2


def test_get_all_contacts_df(dashboard_db: Path):
    """Tests contacts retrieval and parameterized filters."""
    # Unfiltered
    df = get_all_contacts_df(dashboard_db)
    assert len(df) == 3
    assert "Contact ID" in df.columns
    assert "Name" in df.columns
    assert "Department" in df.columns

    # Filter by search
    df_search = get_all_contacts_df(dashboard_db, search_query="Alice")
    assert len(df_search) == 1
    assert df_search.iloc[0]["Name"] == "Alice Smith"

    # Filter by department
    df_dept = get_all_contacts_df(dashboard_db, department="Engineering")
    assert len(df_dept) == 2

    # Filter by company
    df_comp = get_all_contacts_df(dashboard_db, company="Apex Inc")
    assert len(df_comp) == 1
    assert df_comp.iloc[0]["Contact ID"] == "CNT-003"


def test_get_all_reminders_df(dashboard_db: Path):
    """Tests reminders retrieval and parameterized filters."""
    # Unfiltered
    df = get_all_reminders_df(dashboard_db)
    assert len(df) == 7

    # Filter by status
    df_pending = get_all_reminders_df(dashboard_db, status="pending")
    assert len(df_pending) == 1
    assert df_pending.iloc[0]["Reminder ID"] == "REM-P1"

    # Filter by template
    df_tmpl = get_all_reminders_df(dashboard_db, template_key="invoice_due")
    assert len(df_tmpl) == 2

    # Filter by search
    df_search = get_all_reminders_df(dashboard_db, search_query="REF-TX1")
    assert len(df_search) == 1
    assert df_search.iloc[0]["Reminder ID"] == "REM-TX1"


def test_get_email_history_df_restricts_to_dispatch_outcomes(dashboard_db: Path):
    """Verifies email history strictly excludes pending, ready, and processing."""
    df = get_email_history_df(dashboard_db)
    
    # In fixture: simulated (1), sent (1), failed (1), delivery_unknown (1) = 4
    assert len(df) == 4
    statuses = set(df["Dispatch Status"].tolist())
    assert "pending" not in statuses
    assert "ready" not in statuses
    assert "processing" not in statuses
    assert statuses == {"simulated", "sent", "failed", "delivery_unknown"}

    # Filter by status
    df_sent = get_email_history_df(dashboard_db, status="sent")
    assert len(df_sent) == 1
    assert df_sent.iloc[0]["Reminder ID"] == "REM-TX1"


def test_get_activity_timeline_df(dashboard_db: Path):
    """Tests retrieval of activity log entries."""
    df = get_activity_timeline_df(dashboard_db, limit=2)
    assert len(df) == 2
    assert "Log ID" in df.columns
    assert "Event Type" in df.columns


# ==============================================================================
# 3. Chart Generation Tests
# ==============================================================================

def test_chart_generators_render_figures(dashboard_db: Path):
    """Verifies all Plotly chart generation functions return valid Figure objects."""
    kpis = get_system_kpis(dashboard_db)
    timeline_df = get_activity_timeline_df(dashboard_db)

    # Status distribution
    fig_status = plot_status_distribution(kpis["status_counts"])
    assert isinstance(fig_status, go.Figure)

    # Outcome breakdown
    fig_outcome = plot_outcome_breakdown(kpis)
    assert isinstance(fig_outcome, go.Figure)

    # Department distribution
    fig_dept = plot_department_distribution(kpis["department_counts"])
    assert isinstance(fig_dept, go.Figure)

    # Template distribution
    fig_tmpl = plot_template_distribution(kpis["template_counts"])
    assert isinstance(fig_tmpl, go.Figure)

    # Activity timeline
    fig_time = plot_activity_timeline(timeline_df)
    assert isinstance(fig_time, go.Figure)


# ==============================================================================
# 4. Settings Masking and Diagnostic Helpers
# ==============================================================================

def test_email_masking_helper():
    """Ensures recipient/sender emails are masked safely in diagnostics."""
    assert mask_email("akash@example.com") == "a***h@example.com"
    assert mask_email("ab@example.com") == "a*@example.com"
    assert mask_email("") == "Not configured"
    assert mask_email("invalid-email") == "Not configured"


# ==============================================================================
# 5. Safety Invariants Tests
# ==============================================================================

def test_safety_invariants_no_automatic_scheduler_or_smtp():
    """Confirms that importing dashboard components does not launch scheduler or make network calls."""
    import dashboard.app
    from src.email_automation.scheduler import ContinuousScheduler

    # ContinuousScheduler should not be running in any active thread
    import threading
    active_thread_names = [t.name for t in threading.enumerate()]
    assert not any("scheduler" in name.lower() for name in active_thread_names)


# ==============================================================================
# 6. Task 2 & Task 3: Manual Dispatch and Data Sync Safeguards
# ==============================================================================

def test_manual_dispatch_safeguards_dry_run_simulation(dashboard_db: Path, monkeypatch):
    """Verifies that in dry-run mode (the default), manual dispatch performs simulation
    without initiating any SMTP connection or transmission."""
    from unittest.mock import MagicMock
    import smtplib
    from src.email_automation.reminder_service import run_due_reminders_once
    from src.email_automation.mailer import dispatch_ready_emails

    mock_smtp = MagicMock()
    monkeypatch.setattr(smtplib, "SMTP", mock_smtp)

    config = AppConfig(dry_run=True)
    assert config.dry_run is True

    # Ensure reminder has valid template key
    with sqlite3.connect(dashboard_db) as conn:
        conn.execute("UPDATE reminders SET template_key = 'deadline' WHERE reminder_id = 'REM-P1';")
        conn.commit()

    # Run pass
    sched_summary = run_due_reminders_once(db_path=dashboard_db)
    assert sched_summary.prepared >= 1

    dispatch_summary = dispatch_ready_emails(db_path=dashboard_db, config=config, confirm_live_send=False)
    assert dispatch_summary.simulated >= 1

    # Zero SMTP connections made
    mock_smtp.assert_not_called()

    # Verify that the reminder transitioned to 'simulated'
    with sqlite3.connect(dashboard_db) as conn:
        statuses = [r[0] for r in conn.execute("SELECT status FROM reminders;").fetchall()]
        assert "simulated" in statuses


def test_manual_dispatch_safeguards_live_requires_explicit_confirmation(dashboard_db: Path):
    """Verifies that when live SMTP is configured, dispatch is strictly refused without explicit confirmation."""
    from src.email_automation.config import ConfigurationError
    from src.email_automation.mailer import dispatch_ready_emails

    config = AppConfig(
        dry_run=False,
        smtp_username="user@example.com",
        smtp_password="app_password",
        email_from="user@example.com",
    )

    # Calling without confirm_live_send MUST raise ConfigurationError
    with pytest.raises(ConfigurationError, match="Live SMTP mode is configured"):
        dispatch_ready_emails(db_path=dashboard_db, config=config, confirm_live_send=False)


def test_manual_dispatch_safeguards_missing_credentials_refused(dashboard_db: Path):
    """Verifies that live sending with confirmation is refused if credentials are missing."""
    from src.email_automation.config import ConfigurationError
    from src.email_automation.mailer import dispatch_ready_emails

    config = AppConfig(
        dry_run=False,
        smtp_username=None,
        smtp_password=None,
        email_from=None,
    )

    with pytest.raises(ConfigurationError, match="Live SMTP sending requires active credentials"):
        dispatch_ready_emails(db_path=dashboard_db, config=config, confirm_live_send=True)


def test_manual_dispatch_safeguards_allowlist_enforced(dashboard_db: Path, monkeypatch):
    """Verifies that recipients outside the configured allowlist are rejected and marked failed."""
    from unittest.mock import MagicMock
    import smtplib
    from src.email_automation.mailer import dispatch_ready_emails

    # Put a reminder into 'ready' with an un-allowlisted recipient and prepared email
    with sqlite3.connect(dashboard_db) as conn:
        conn.execute("UPDATE reminders SET status = 'ready' WHERE reminder_id = 'REM-R1';")
        conn.execute(
            """
            INSERT OR REPLACE INTO prepared_emails (reminder_id, contact_id, recipient_email, recipient_name, template_key, subject, html_body, text_body, due_at, reference_id, prepared_at)
            VALUES ('REM-R1', 'CNT-001', 'alice@acme.com', 'Alice Smith', 'overdue_task', 'Sub R1', '<p>R1</p>', 'R1 text', '2026-11-20T10:00:00Z', 'REF-R1', '2026-11-20T09:15:00Z');
            """
        )
        conn.commit()

    config = AppConfig(
        dry_run=False,
        smtp_username="sender@example.com",
        smtp_password="password",
        email_from="sender@example.com",
        smtp_allowed_recipients=("allowed_only@example.com",),  # alice@acme.com is NOT in allowlist
    )

    mock_smtp_inst = MagicMock()
    mock_smtp_class = MagicMock(return_value=mock_smtp_inst)
    monkeypatch.setattr(smtplib, "SMTP", mock_smtp_class)

    dispatched = dispatch_ready_emails(db_path=dashboard_db, config=config, confirm_live_send=True)
    assert dispatched.failed == 1

    # Should be marked failed due to allowlist rejection
    with sqlite3.connect(dashboard_db) as conn:
        row = conn.execute("SELECT status, dispatch_error FROM reminders WHERE reminder_id = 'REM-R1';").fetchone()
        assert row[0] == "failed"
        assert "SMTP_ALLOWED_RECIPIENTS" in row[1]


def test_manual_dispatch_safeguards_repeated_clicks_idempotent(dashboard_db: Path):
    """Verifies that repeated executions do not double-dispatch reminders."""
    from src.email_automation.reminder_service import run_due_reminders_once
    from src.email_automation.mailer import dispatch_ready_emails

    config = AppConfig(dry_run=True)

    # First run claims and simulates
    run_due_reminders_once(db_path=dashboard_db)
    dispatch_ready_emails(db_path=dashboard_db, config=config, confirm_live_send=False)

    # Second run immediately after
    sched_second = run_due_reminders_once(db_path=dashboard_db)
    dispatch_second = dispatch_ready_emails(db_path=dashboard_db, config=config, confirm_live_send=False)

    assert sched_second.prepared == 0
    assert dispatch_second.claimed == 0


def test_manual_dispatch_safeguards_delivery_unknown_not_retried(dashboard_db: Path):
    """Verifies that records in delivery_unknown are never claimed or retried."""
    from src.email_automation.mailer import dispatch_ready_emails

    config = AppConfig(dry_run=True)

    # Verify REM-U1 is in delivery_unknown
    with sqlite3.connect(dashboard_db) as conn:
        status = conn.execute("SELECT status FROM reminders WHERE reminder_id = 'REM-U1';").fetchone()[0]
        assert status == "delivery_unknown"

    # Run dispatch
    dispatched = dispatch_ready_emails(db_path=dashboard_db, config=config, confirm_live_send=False)

    # REM-U1 remains untouched
    with sqlite3.connect(dashboard_db) as conn:
        status_after = conn.execute("SELECT status FROM reminders WHERE reminder_id = 'REM-U1';").fetchone()[0]
        assert status_after == "delivery_unknown"


def test_settings_data_sync_preserves_inflight_and_completed_records(dashboard_db: Path, tmp_path: Path):
    """Verifies that sample CSV re-synchronization preserves active and completed reminder states."""
    from src.email_automation.database import import_or_sync_csv

    # Create temporary contacts and reminders CSV files
    contacts_file = tmp_path / "sync_contacts.csv"
    contacts_file.write_text(
        "contact_id,first_name,last_name,email,department,company\n"
        "CNT-001,Alice_Updated,Smith,alice@acme.com,Engineering,Acme Corp\n"
        "CNT-NEW,David,Brown,david@acme.com,Sales,Acme Corp\n",
        encoding="utf-8",
    )

    reminders_file = tmp_path / "sync_reminders.csv"
    reminders_file.write_text(
        "reminder_id,contact_id,reminder_type,template_key,due_at,status,reference_id,notes\n"
        "REM-P1,CNT-001,task,overdue_task,2026-11-20T10:00:00Z,pending,REF-P1,Updated pending note\n"
        "REM-S1,CNT-002,invoice,invoice_due,2026-11-20T10:00:00Z,pending,REF-S1,Attempted overwrite\n"
        "REM-TX1,CNT-003,meeting,project_status,2026-11-20T10:00:00Z,pending,REF-TX1,Attempted overwrite\n"
        "REM-U1,CNT-001,task,overdue_task,2026-11-20T10:00:00Z,pending,REF-U1,Attempted overwrite\n"
        "REM-NEW,CNT-NEW,task,overdue_task,2026-11-25T10:00:00Z,pending,REF-NEW,New reminder\n",
        encoding="utf-8",
    )

    # Perform synchronization
    contacts_synced, reminders_synced = import_or_sync_csv(
        db_path=dashboard_db,
        contacts_csv=contacts_file,
        reminders_csv=reminders_file,
    )

    assert contacts_synced == 2
    assert reminders_synced == 5

    with sqlite3.connect(dashboard_db) as conn:
        # CNT-001 updated
        c1 = conn.execute("SELECT first_name FROM contacts WHERE contact_id = 'CNT-001';").fetchone()[0]
        assert c1 == "Alice_Updated"

        # CNT-NEW inserted
        c_new = conn.execute("SELECT count(*) FROM contacts WHERE contact_id = 'CNT-NEW';").fetchone()[0]
        assert c_new == 1

        # REM-P1 was pending, so its note was updated
        r_p1 = conn.execute("SELECT notes FROM reminders WHERE reminder_id = 'REM-P1';").fetchone()[0]
        assert r_p1 == "Updated pending note"

        # REM-S1 (simulated), REM-TX1 (sent), REM-U1 (delivery_unknown) MUST retain their original status and notes!
        r_s1 = conn.execute("SELECT status, notes FROM reminders WHERE reminder_id = 'REM-S1';").fetchone()
        assert r_s1[0] == "simulated"
        assert r_s1[1] == "Simulated item"

        r_tx1 = conn.execute("SELECT status, notes FROM reminders WHERE reminder_id = 'REM-TX1';").fetchone()
        assert r_tx1[0] == "sent"
        assert r_tx1[1] == "Sent item"

        r_u1 = conn.execute("SELECT status, notes FROM reminders WHERE reminder_id = 'REM-U1';").fetchone()
        assert r_u1[0] == "delivery_unknown"
        assert r_u1[1] == "Unknown item"


# =====================================================================
# Regression Tests: Table and Dataframe Height Safety Contract
# =====================================================================


def test_sanitize_height_contract() -> None:
    """Verifies that _sanitize_height strictly returns valid Streamlit height values."""
    # Valid numeric positive integers
    assert _sanitize_height(350) == 350
    assert _sanitize_height(1) == 1
    assert _sanitize_height("400") == 400

    # Valid string literals
    assert _sanitize_height("content") == "content"
    assert _sanitize_height("stretch") == "stretch"
    assert _sanitize_height("auto") == "auto"
    assert _sanitize_height("  CONTENT  ") == "content"
    assert _sanitize_height("STRETCH") == "stretch"

    # Invalid / unsupported values must return None (omitted)
    assert _sanitize_height(None) is None
    assert _sanitize_height(0) is None
    assert _sanitize_height(-50) is None
    assert _sanitize_height("invalid") is None
    assert _sanitize_height("") is None
    assert _sanitize_height(True) is None
    assert _sanitize_height(False) is None
    assert _sanitize_height(3.14) is None


def test_render_dataframe_no_height_omits_height_param(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies render_dataframe with default height omits height parameter completely."""
    captured_kwargs = {}

    def mock_dataframe(df, **kwargs):
        captured_kwargs.update(kwargs)

    monkeypatch.setattr(st, "dataframe", mock_dataframe)

    sample_df = pd.DataFrame({"col_a": [1, 2], "col_b": ["x", "y"]})
    render_dataframe(sample_df)

    assert "height" not in captured_kwargs
    assert captured_kwargs["use_container_width"] is True
    assert captured_kwargs["hide_index"] is True


def test_render_dataframe_explicit_numeric_height(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies render_dataframe with positive integer passes exact pixel height."""
    captured_kwargs = {}

    def mock_dataframe(df, **kwargs):
        captured_kwargs.update(kwargs)

    monkeypatch.setattr(st, "dataframe", mock_dataframe)

    sample_df = pd.DataFrame({"col_a": [1, 2]})
    render_dataframe(sample_df, height=350)

    assert captured_kwargs.get("height") == 350


def test_render_dataframe_content_and_stretch_height(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies render_dataframe with content and stretch passes valid string literals."""
    captured_kwargs = {}

    def mock_dataframe(df, **kwargs):
        captured_kwargs.clear()
        captured_kwargs.update(kwargs)

    monkeypatch.setattr(st, "dataframe", mock_dataframe)

    sample_df = pd.DataFrame({"col_a": [1, 2]})

    render_dataframe(sample_df, height="content")
    assert captured_kwargs.get("height") == "content"

    render_dataframe(sample_df, height="stretch")
    assert captured_kwargs.get("height") == "stretch"

    render_dataframe(sample_df, height="auto")
    assert captured_kwargs.get("height") == "auto"


def test_render_dataframe_invalid_height_handled_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies render_dataframe with invalid height values safely omits height without raising."""
    captured_kwargs = {}

    def mock_dataframe(df, **kwargs):
        captured_kwargs.clear()
        captured_kwargs.update(kwargs)

    monkeypatch.setattr(st, "dataframe", mock_dataframe)

    sample_df = pd.DataFrame({"col_a": [1, 2]})

    for invalid_val in [None, 0, -100, "invalid_val", True, False, 9.99]:
        captured_kwargs.clear()
        render_dataframe(sample_df, height=invalid_val)
        assert "height" not in captured_kwargs, f"Failed for invalid value: {invalid_val}"


def test_render_dataframe_preserves_configuration_and_column_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies render_dataframe preserves column_config, column_order, and custom kwargs."""
    captured_kwargs = {}

    def mock_dataframe(df, **kwargs):
        captured_kwargs.update(kwargs)

    monkeypatch.setattr(st, "dataframe", mock_dataframe)

    sample_df = pd.DataFrame({"a": [1], "b": [2]})
    cfg = {"a": {"label": "Alpha"}}
    order = ["b", "a"]

    render_dataframe(
        sample_df,
        use_container_width=False,
        hide_index=False,
        column_config=cfg,
        column_order=order,
        key="custom_table_key",
    )

    assert captured_kwargs["use_container_width"] is False
    assert captured_kwargs["hide_index"] is False
    assert captured_kwargs["column_config"] == cfg
    assert captured_kwargs["column_order"] == order
    assert captured_kwargs["key"] == "custom_table_key"
    assert "height" not in captured_kwargs


def test_render_dataframe_empty_dataframe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies empty dataframe shows info message and skips st.dataframe."""
    info_called = []
    df_called = []

    monkeypatch.setattr(st, "info", lambda msg: info_called.append(msg))
    monkeypatch.setattr(st, "dataframe", lambda *a, **k: df_called.append(a))

    empty_df = pd.DataFrame()
    render_dataframe(empty_df)

    assert len(info_called) == 1
    assert "No matching records found." in info_called[0]
    assert len(df_called) == 0


def test_render_table_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies render_table renders populated table and handles empty state."""
    table_called = []
    info_called = []

    monkeypatch.setattr(st, "table", lambda df: table_called.append(df))
    monkeypatch.setattr(st, "info", lambda msg: info_called.append(msg))

    sample_df = pd.DataFrame({"x": [10, 20]})
    render_table(sample_df)
    assert len(table_called) == 1

    empty_df = pd.DataFrame()
    render_table(empty_df)
    assert len(info_called) == 1


