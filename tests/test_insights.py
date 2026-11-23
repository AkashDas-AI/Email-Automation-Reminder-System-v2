"""Unit and Integration Tests for Phase 11 — Insights & Interpretation

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Comprehensive test coverage for status analysis, dispatch performance formulas,
lead-time temporal distributions, department concentration, operational workload alerts,
and the Phase 11 automated interpretation engine.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
import plotly.graph_objects as go

from src.email_automation.database import init_db
from src.email_automation.insights import (
    get_system_kpis,
    get_reminder_status_metrics,
    get_dispatch_performance_metrics,
    get_time_distribution_metrics,
    get_department_and_company_metrics,
    get_category_and_template_metrics,
    get_operational_workload_metrics,
    generate_system_interpretations,
)
from dashboard.components.charts import (
    plot_company_distribution,
    plot_category_distribution,
    plot_lead_time_distribution,
    plot_temporal_due_distribution,
    plot_overdue_vs_upcoming,
)


@pytest.fixture
def analytics_db(tmp_path: Path) -> Path:
    """Creates a temporary test database populated with known records across all categories and statuses."""
    db_file = tmp_path / "analytics_test.db"
    init_db(db_file)

    with sqlite3.connect(db_file) as conn:
        # Insert contacts across departments and companies
        conn.execute(
            """
            INSERT INTO contacts (contact_id, first_name, last_name, email, department, company, created_at)
            VALUES 
                ('CNT-01', 'Alice', 'Smith', 'alice@acme.com', 'Engineering', 'Acme Corp', '2026-11-20T10:00:00Z'),
                ('CNT-02', 'Bob', 'Jones', 'bob@acme.com', 'Engineering', 'Acme Corp', '2026-11-20T10:00:00Z'),
                ('CNT-03', 'Carol', 'Taylor', 'carol@apex.com', 'Marketing', 'Apex Inc', '2026-11-20T10:00:00Z'),
                ('CNT-04', 'David', 'Miller', 'david@apex.com', 'Finance', 'Apex Inc', '2026-11-20T10:00:00Z');
            """
        )

        # Baseline as_of time: 2026-11-22T12:00:00Z
        # Insert reminders across all statuses and date horizons
        conn.execute(
            """
            INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at)
            VALUES
                -- Overdue items (due_at < 2026-11-22, actionable)
                ('REM-OD1', 'CNT-01', 'meeting', 'meeting', '2026-11-20T10:00:00Z', 'pending', 'REF-OD1', 'Overdue pending', '2026-11-19T00:00:00Z', '2026-11-19T00:00:00Z'),
                ('REM-OD2', 'CNT-02', 'deadline', 'deadline', '2026-11-21T10:00:00Z', 'ready', 'REF-OD2', 'Overdue ready', '2026-11-19T00:00:00Z', '2026-11-19T00:00:00Z'),

                -- In-flight / ambiguous items
                ('REM-PR1', 'CNT-03', 'payment', 'payment', '2026-11-22T10:00:00Z', 'processing', 'REF-PR1', 'Processing item', '2026-11-21T00:00:00Z', '2026-11-21T00:00:00Z'),
                ('REM-DU1', 'CNT-01', 'follow_up', 'follow_up', '2026-11-20T15:00:00Z', 'delivery_unknown', 'REF-DU1', 'Ambiguous send', '2026-11-20T00:00:00Z', '2026-11-20T16:00:00Z'),

                -- Dispatched outcomes (historical, NOT overdue even though due_at is past)
                ('REM-SIM1', 'CNT-02', 'meeting', 'meeting', '2026-11-20T09:00:00Z', 'simulated', 'REF-SIM1', 'Simulated 1', '2026-11-19T00:00:00Z', '2026-11-20T09:05:00Z'),
                ('REM-SIM2', 'CNT-03', 'general', 'general', '2026-11-21T09:00:00Z', 'simulated', 'REF-SIM2', 'Simulated 2', '2026-11-19T00:00:00Z', '2026-11-21T09:05:00Z'),
                ('REM-TX1', 'CNT-04', 'payment', 'payment', '2026-11-21T14:00:00Z', 'sent', 'REF-TX1', 'Sent 1', '2026-11-19T00:00:00Z', '2026-11-21T14:05:00Z'),
                ('REM-F1', 'CNT-04', 'deadline', 'deadline', '2026-11-21T16:00:00Z', 'failed', 'REF-F1', 'Failed 1', '2026-11-19T00:00:00Z', '2026-11-21T16:05:00Z'),

                -- Upcoming items (due_at > 2026-11-22T12:00:00Z)
                -- 1 in next 24h
                ('REM-UP1', 'CNT-01', 'meeting', 'meeting', '2026-11-22T18:00:00Z', 'pending', 'REF-UP1', 'Next 24h', '2026-11-22T00:00:00Z', '2026-11-22T00:00:00Z'),
                -- 1 in next 7d
                ('REM-UP2', 'CNT-02', 'deadline', 'deadline', '2026-11-25T10:00:00Z', 'pending', 'REF-UP2', 'Next 7d', '2026-11-22T00:00:00Z', '2026-11-22T00:00:00Z'),
                -- 1 in next 30d
                ('REM-UP3', 'CNT-03', 'payment', 'payment', '2026-12-05T10:00:00Z', 'pending', 'REF-UP3', 'Next 30d', '2026-11-22T00:00:00Z', '2026-11-22T00:00:00Z'),
                -- 2 beyond 30d (January 2027)
                ('REM-UP4', 'CNT-01', 'meeting', 'meeting', '2027-01-10T10:00:00Z', 'pending', 'REF-UP4', 'Jan 2027 #1', '2026-11-22T00:00:00Z', '2026-11-22T00:00:00Z'),
                ('REM-UP5', 'CNT-02', 'follow_up', 'follow_up', '2027-01-15T10:00:00Z', 'pending', 'REF-UP5', 'Jan 2027 #2', '2026-11-22T00:00:00Z', '2026-11-22T00:00:00Z');
            """
        )

        # Activity logs
        conn.execute(
            """
            INSERT INTO activity_logs (timestamp, event_type, severity, reminder_id, contact_id, status, message, details)
            VALUES
                ('2026-11-20T09:05:00Z', 'email_simulated', 'INFO', 'REM-SIM1', 'CNT-02', 'success', 'Simulated', NULL),
                ('2026-11-21T09:05:00Z', 'email_simulated', 'INFO', 'REM-SIM2', 'CNT-03', 'success', 'Simulated', NULL),
                ('2026-11-21T14:05:00Z', 'email_sent', 'INFO', 'REM-TX1', 'CNT-04', 'success', 'Sent', NULL),
                ('2026-11-21T16:05:00Z', 'dispatch_failed', 'ERROR', 'REM-F1', 'CNT-04', 'failure', 'Auth error', NULL);
            """
        )
        conn.commit()

    return db_file


@pytest.fixture
def future_sample_db(tmp_path: Path) -> Path:
    """Creates a temporary test database representing the actual 24-reminder January 2027 sample dataset."""
    db_file = tmp_path / "sample_test.db"
    init_db(db_file)

    with sqlite3.connect(db_file) as conn:
        # Insert 4 contacts
        conn.execute(
            """
            INSERT INTO contacts (contact_id, first_name, last_name, email, department, company, created_at)
            VALUES 
                ('CNT-01', 'Aarav', 'Sharma', 'aarav@apex.com', 'IT', 'Apex Corp', '2026-11-20T10:00:00Z'),
                ('CNT-02', 'Diya', 'Patel', 'diya@apex.com', 'IT', 'Apex Corp', '2026-11-20T10:00:00Z'),
                ('CNT-03', 'Rohan', 'Verma', 'rohan@crestline.com', 'Finance', 'Crestline', '2026-11-20T10:00:00Z'),
                ('CNT-04', 'Ananya', 'Iyer', 'ananya@nexus.com', 'Marketing', 'Nexus', '2026-11-20T10:00:00Z');
            """
        )

        # 24 pending reminders in Jan 2027
        for i in range(1, 25):
            r_id = f"REM{i:03d}"
            c_id = f"CNT-{((i % 4) + 1):02d}"
            day = 10 + (i % 15)
            cat = ["meeting", "deadline", "payment", "follow_up", "general"][i % 5]
            conn.execute(
                """
                INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, 'Sample note', '2026-11-20T10:00:00Z', '2026-11-20T10:00:00Z');
                """,
                [r_id, c_id, cat, cat, f"2027-01-{day:02d}T10:00:00Z", f"REF-{i}"],
            )
        conn.commit()

    return db_file


# =====================================================================
# Tests: Reminder Status Analysis & Temporal Boundaries
# =====================================================================

def test_reminder_status_metrics_all_seven_statuses(analytics_db: Path) -> None:
    """Verifies that reminder status metrics accurately aggregate counts across all 7 statuses."""
    m = get_reminder_status_metrics(analytics_db)

    assert m["total_reminders"] == 13
    assert m["pending"] == 6
    assert m["ready"] == 1
    assert m["processing"] == 1
    assert m["simulated"] == 2
    assert m["sent"] == 1
    assert m["failed"] == 1
    assert m["delivery_unknown"] == 1

    # Invariant: sum of all 7 statuses must equal total_reminders
    sum_all = sum(m["all_statuses"].values())
    assert sum_all == m["total_reminders"]


def test_overdue_vs_upcoming_calculation_with_timezone(analytics_db: Path) -> None:
    """Verifies that overdue vs upcoming reminders are accurately partitioned based on as_of UTC."""
    as_of = datetime(2026, 11, 22, 12, 0, 0, tzinfo=timezone.utc)
    m = get_reminder_status_metrics(analytics_db, as_of=as_of)

    # Overdue: due_at <= 2026-11-22T12:00:00Z AND status in ('pending', 'ready')
    # REM-OD1 (pending), REM-OD2 (ready) = 2
    assert m["overdue_count"] == 2
    assert m["overdue_pct"] == round(2 / 13 * 100.0, 1)

    # Upcoming: due_at > 2026-11-22T12:00:00Z
    # REM-UP1, REM-UP2, REM-UP3, REM-UP4, REM-UP5 = 5
    assert m["upcoming_count"] == 5
    assert m["upcoming_pct"] == round(5 / 13 * 100.0, 1)

    # Dispatched items (REM-SIM1, REM-SIM2, REM-TX1, REM-F1, REM-DU1, REM-PR1) are NOT counted as actionable overdue
    assert m["past_due_total"] == 8


# =====================================================================
# Tests: Dispatch Performance Formulas & Zero Denominator Protection
# =====================================================================

def test_dispatch_performance_strict_formula(analytics_db: Path) -> None:
    """Verifies that dispatch success rate strictly uses Attempted = Simulated + Sent + Failed."""
    p = get_dispatch_performance_metrics(analytics_db)

    # simulated=2, sent=1, failed=1, delivery_unknown=1
    assert p["simulated"] == 2
    assert p["smtp_accepted"] == 1
    assert p["failed"] == 1
    assert p["delivery_unknown"] == 1

    # Attempted = 2 + 1 + 1 = 4 (excludes delivery_unknown, pending, ready, processing)
    assert p["attempted"] == 4
    assert p["has_attempted"] is True

    # Success rate = (2 + 1) / 4 * 100 = 75.0%
    assert p["success_rate"] == 75.0
    assert p["formatted_success_rate"] == "75.0%"
    assert "not verified receipt" in p["smtp_delivery_clarification"]


def test_dispatch_performance_zero_denominator_safe(future_sample_db: Path) -> None:
    """Verifies that zero attempted dispatches safely sets success_rate to None without dividing by zero."""
    p = get_dispatch_performance_metrics(future_sample_db)

    assert p["attempted"] == 0
    assert p["has_attempted"] is False
    assert p["success_rate"] is None
    assert p["formatted_success_rate"] == "N/A (0 attempts)"
    assert p["delivery_unknown"] == 0


# =====================================================================
# Tests: Temporal Horizons & Lead-Time Buckets
# =====================================================================

def test_time_distribution_metrics(analytics_db: Path) -> None:
    """Verifies that time distribution accurately groups by day, month, and lead-time buckets."""
    as_of = datetime(2026, 11, 22, 12, 0, 0, tzinfo=timezone.utc)
    t = get_time_distribution_metrics(analytics_db, as_of=as_of)

    # Lead time buckets for actionable items (status in pending, ready):
    # Next 24h: REM-UP1 (due 2026-11-22T18:00:00Z) = 1
    # Next 7d: REM-UP1, REM-UP2 = 2
    # Next 30d: REM-UP1, REM-UP2, REM-UP3 = 3
    # Beyond 30d: REM-UP4, REM-UP5 (Jan 2027) = 2
    buckets = t["lead_time_buckets"]
    assert buckets["due_next_24h"] == 1
    assert buckets["due_next_7d"] == 2
    assert buckets["due_next_30d"] == 3
    assert buckets["due_beyond_30d"] == 2

    # Grouping by month
    assert "2026-11" in t["by_month"]
    assert "2026-12" in t["by_month"]
    assert "2027-01" in t["by_month"]


# =====================================================================
# Tests: Department & Company Concentration & Small Sample Caveats
# =====================================================================

def test_department_and_company_metrics(analytics_db: Path) -> None:
    """Verifies department workload concentration and small-sample detection."""
    d = get_department_and_company_metrics(analytics_db)

    assert d["total_reminders"] == 13
    assert d["total_contacts"] == 4
    assert d["top_department"] == "Engineering"
    assert d["top_company"] == "Acme Corp"

    # Engineering has CNT-01 (4 reminders) + CNT-02 (4 reminders) = 8
    assert d["top_department_count"] == 8
    assert d["top_department_pct"] == round(8 / 13 * 100.0, 1)

    # Acme Corp has CNT-01 (4) + CNT-02 (4) = 8
    assert d["top_company_count"] == 8
    assert d["top_company_pct"] == round(8 / 13 * 100.0, 1)

    # Small sample detection
    assert d["is_small_sample"] is True
    assert "reflect operational workload distribution" in d["sample_size_caveat"]


# =====================================================================
# Tests: Category & Template Analysis
# =====================================================================

def test_category_and_template_metrics(analytics_db: Path) -> None:
    """Verifies reminder category and template key distribution."""
    c = get_category_and_template_metrics(analytics_db)

    assert c["total_reminders"] == 13
    assert "meeting" in c["category_counts"]
    assert "deadline" in c["category_counts"]
    assert "payment" in c["category_counts"]
    assert "follow_up" in c["category_counts"]
    assert "general" in c["category_counts"]

    # Top category
    assert c["top_category"] == "meeting"
    assert c["top_category_count"] == 4


# =====================================================================
# Tests: Operational Workload Bottlenecks & Alerts
# =====================================================================

def test_operational_workload_metrics(analytics_db: Path) -> None:
    """Verifies operational bottleneck detection, overdue identification, and alert tracking."""
    as_of = datetime(2026, 11, 22, 12, 0, 0, tzinfo=timezone.utc)
    op = get_operational_workload_metrics(analytics_db, as_of=as_of)

    assert op["overdue_count"] == 2
    assert len(op["overdue_items"]) == 2
    assert op["delivery_unknown_count"] == 1
    assert len(op["delivery_unknown_items"]) == 1
    assert op["processing_count"] == 1
    assert op["orphan_reminder_count"] == 0


# =====================================================================
# Tests: Automated Interpretation Engine
# =====================================================================

def test_interpretation_engine_sample_data(future_sample_db: Path) -> None:
    """Verifies that interpretation engine produces accurate, objective findings for the 24-reminder sample dataset."""
    as_of = datetime(2026, 11, 22, 12, 0, 0, tzinfo=timezone.utc)
    interps = generate_system_interpretations(future_sample_db, as_of=as_of)

    assert len(interps) == 5

    titles = [item["title"] for item in interps]
    assert "Department Workload Concentration" in titles
    assert "Primary Reminder Category" in titles
    assert "Due Date & Lead-Time Analysis" in titles
    assert "Email Dispatch Execution & Handover" in titles
    assert "System Health & Integrity Status" in titles

    # Schedule interpretation must confirm zero overdue
    sched = next(item for item in interps if item["title"] == "Due Date & Lead-Time Analysis")
    assert "Zero reminders are overdue" in sched["finding"]
    assert sched["severity"] == "success"

    # Dispatch interpretation must confirm zero dispatches attempted yet without false 0% failure
    disp = next(item for item in interps if item["title"] == "Email Dispatch Execution & Handover")
    assert "Zero dispatches have been attempted yet" in disp["finding"]
    assert "N/A" in disp["finding"]
    assert disp["severity"] == "neutral"

    # Health interpretation must confirm all systems healthy
    health = next(item for item in interps if item["title"] == "System Health & Integrity Status")
    assert "System Integrity Verified" in health["finding"]
    assert health["severity"] == "success"


def test_interpretation_engine_empty_database(tmp_path: Path) -> None:
    """Verifies interpretation engine gracefully handles an empty database."""
    empty_db = tmp_path / "empty.db"
    init_db(empty_db)

    interps = generate_system_interpretations(empty_db)
    assert len(interps) == 1
    assert interps[0]["title"] == "Insufficient Data for Analysis"
    assert "zero reminder records" in interps[0]["finding"]
    assert interps[0]["severity"] == "neutral"


def test_interpretation_engine_operational_alert_trigger(analytics_db: Path) -> None:
    """Verifies that delivery_unknown and processing items trigger operational attention."""
    as_of = datetime(2026, 11, 22, 12, 0, 0, tzinfo=timezone.utc)
    interps = generate_system_interpretations(analytics_db, as_of=as_of)

    health = next(item for item in interps if item["title"] == "System Health & Integrity Status")
    assert health["severity"] == "warning"
    assert "Operational Attention Required" in health["finding"]
    assert "delivery_unknown" in health["finding"]


# =====================================================================
# Tests: Phase 11 Visual Chart Component Generation
# =====================================================================

def test_charts_rendering_for_all_phase11_visualizations() -> None:
    """Verifies all Phase 11 Plotly chart generators produce valid go.Figure objects with dark theme."""
    f1 = plot_company_distribution({"Acme": 5, "Apex": 3})
    assert isinstance(f1, go.Figure)

    f2 = plot_category_distribution({"meeting": 10, "deadline": 5})
    assert isinstance(f2, go.Figure)

    f3 = plot_lead_time_distribution({"due_next_24h": 1, "due_next_7d": 4, "due_next_30d": 10, "due_beyond_30d": 9})
    assert isinstance(f3, go.Figure)

    f4 = plot_temporal_due_distribution({"2027-01-10": 2, "2027-01-11": 3})
    assert isinstance(f4, go.Figure)

    f5 = plot_overdue_vs_upcoming(0, 24)
    assert isinstance(f5, go.Figure)

    f6 = plot_overdue_vs_upcoming(0, 0)
    assert isinstance(f6, go.Figure)


# =====================================================================
# Tests: Phase 11 Analytical Correctness Audit Tests
# =====================================================================

def test_upcoming_actionable_workload_strict_status_filtering(tmp_path: Path) -> None:
    """Verifies that upcoming actionable workload includes only pending or ready records,
    and strictly excludes completed or terminal statuses (simulated, sent, failed, delivery_unknown).
    """
    db_file = tmp_path / "upcoming_audit.db"
    init_db(db_file)

    now_utc = datetime(2026, 11, 22, 12, 0, 0, tzinfo=timezone.utc)
    future_date = "2026-11-25T10:00:00Z"
    past_date = "2026-11-20T10:00:00Z"

    with sqlite3.connect(db_file) as conn:
        conn.execute(
            """
            INSERT INTO contacts (contact_id, first_name, last_name, email, department, company, created_at)
            VALUES ('C1', 'Test', 'User', 'test@example.com', 'IT', 'Apex Corp', '2026-11-01T00:00:00Z');
            """
        )

        # 6 future reminders across distinct statuses
        conn.execute(
            f"""
            INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at)
            VALUES
                ('REM-FUT-PENDING', 'C1', 'meeting', 'meeting', '{future_date}', 'pending', 'R1', '', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z'),
                ('REM-FUT-READY', 'C1', 'meeting', 'meeting', '{future_date}', 'ready', 'R2', '', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z'),
                ('REM-FUT-SIMULATED', 'C1', 'meeting', 'meeting', '{future_date}', 'simulated', 'R3', '', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z'),
                ('REM-FUT-SENT', 'C1', 'meeting', 'meeting', '{future_date}', 'sent', 'R4', '', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z'),
                ('REM-FUT-FAILED', 'C1', 'meeting', 'meeting', '{future_date}', 'failed', 'R5', '', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z'),
                ('REM-FUT-UNKNOWN', 'C1', 'meeting', 'meeting', '{future_date}', 'delivery_unknown', 'R6', '', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z'),

                -- 2 past reminders (1 actionable overdue, 1 completed historical)
                ('REM-PAST-PENDING', 'C1', 'meeting', 'meeting', '{past_date}', 'pending', 'R7', '', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z'),
                ('REM-PAST-SENT', 'C1', 'meeting', 'meeting', '{past_date}', 'sent', 'R8', '', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z');
            """
        )
        conn.commit()

    m = get_reminder_status_metrics(db_file, as_of=now_utc)

    # Invariants:
    assert m["total_reminders"] == 8
    # Actionable upcoming workload must ONLY include future pending and future ready (2 records)
    assert m["upcoming_count"] == 2
    assert m["upcoming_actionable_count"] == 2
    # Total future reminders regardless of status is 6
    assert m["future_total"] == 6

    # Active overdue workload must ONLY include past pending (1 record), not past sent
    assert m["overdue_count"] == 1
    # Total historical past-due reminders regardless of status is 2
    assert m["past_due_total"] == 2

    # Verify time distribution lead-time buckets strictly include only actionable records
    t = get_time_distribution_metrics(db_file, as_of=now_utc)
    buckets = t["lead_time_buckets"]
    # 2026-11-25 is within next 7 days and within next 30 days
    assert buckets["due_next_7d"] == 2
    assert buckets["due_next_30d"] == 2
    assert buckets["due_beyond_30d"] == 0
    assert t["total_upcoming_actionable"] == 2


def test_actual_database_sample_data_verification() -> None:
    """Verifies calculated analytics against the actual project SQLite database (reminders.db)."""
    db_path = Path("data/database/reminders.db")
    assert db_path.is_file(), "data/database/reminders.db must exist"

    status_m = get_reminder_status_metrics(db_path)
    dept_m = get_department_and_company_metrics(db_path)
    cat_m = get_category_and_template_metrics(db_path)
    disp_m = get_dispatch_performance_metrics(db_path)

    # 1. Entity totals
    assert status_m["total_reminders"] == 24
    assert dept_m["total_contacts"] == 20

    # 2. Statuses
    assert status_m["pending"] == 24
    assert status_m["ready"] == 0
    assert status_m["overdue_count"] == 0
    assert status_m["upcoming_count"] == 24

    # 3. Department breakdown (IT holds 5 reminders, 20.8%)
    assert dept_m["department_counts"]["IT"] == 5
    assert dept_m["top_department"] == "IT"

    # 4. Template & Category breakdown
    assert cat_m["template_counts"]["deadline"] == 6
    assert cat_m["template_counts"]["meeting"] == 5
    assert cat_m["template_counts"]["follow_up"] == 5
    assert cat_m["template_counts"]["general"] == 4
    assert cat_m["template_counts"]["payment"] == 4

    # 5. Dispatch performance
    assert disp_m["attempted"] == 0
    assert disp_m["has_attempted"] is False
    assert disp_m["success_rate"] is None
    assert disp_m["formatted_success_rate"] == "N/A (0 attempts)"


def test_interpretation_engine_dynamic_rankings(tmp_path: Path) -> None:
    """Verifies that the interpretation engine generates dynamic findings calculated
    from current database values rather than hardcoded conclusions.
    """
    db_file = tmp_path / "dynamic_test.db"
    init_db(db_file)

    now_utc = datetime(2026, 11, 22, 12, 0, 0, tzinfo=timezone.utc)

    with sqlite3.connect(db_file) as conn:
        conn.execute(
            """
            INSERT INTO contacts (contact_id, first_name, last_name, email, department, company, created_at)
            VALUES 
                ('C-HR1', 'Helen', 'Ross', 'helen@corp.com', 'Human Resources', 'Omega Inc', '2026-11-01T00:00:00Z'),
                ('C-ENG', 'Evan', 'Gray', 'evan@corp.com', 'Engineering', 'Alpha Ltd', '2026-11-01T00:00:00Z');
            """
        )

        # 10 HR payment reminders, 2 Engineering meeting reminders
        for i in range(10):
            conn.execute(
                f"""
                INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at)
                VALUES ('REM-HR-{i}', 'C-HR1', 'payment', 'payment', '2026-11-25T10:00:00Z', 'pending', 'R-HR', '', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z');
                """
            )
        for i in range(2):
            conn.execute(
                f"""
                INSERT INTO reminders (reminder_id, contact_id, reminder_type, template_key, due_at, status, reference_id, notes, created_at, updated_at)
                VALUES ('REM-ENG-{i}', 'C-ENG', 'meeting', 'meeting', '2026-11-26T10:00:00Z', 'pending', 'R-ENG', '', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z');
                """
            )
        conn.commit()

    interps = generate_system_interpretations(db_file, as_of=now_utc)

    dept_finding = next(it for it in interps if it["title"] == "Department Workload Concentration")
    assert "Human Resources" in dept_finding["finding"]
    assert "10 of 12" in dept_finding["finding"]
    assert "83.3%" in dept_finding["finding"]

    cat_finding = next(it for it in interps if it["title"] == "Primary Reminder Category")
    assert "Payment" in cat_finding["finding"]
    assert "10 of 12" in cat_finding["finding"]

