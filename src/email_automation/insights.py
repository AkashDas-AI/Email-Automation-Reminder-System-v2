"""Insights & Analytics Module

Project: Email Automation & Reminder System
Author: Akash Das
Responsibility: Analyzes database records to compute operational KPIs, delivery success rates,
reminder status distributions, workload concentrations, and data-grounded interpretations
for the Streamlit dashboard and reporting layers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from .database import DEFAULT_DB_PATH, get_db_connection

logger = logging.getLogger(__name__)


# =====================================================================
# Phase 10 / Backward-Compatible KPI Functions
# =====================================================================

def get_system_kpis(db_path: Union[Path, str] = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Computes comprehensive system-wide operational KPIs from actual database records.
    
    Formula Invariants:
        - attempted = simulated + smtp_accepted (sent) + failed
        - pending, ready, and processing are strictly excluded from the attempted denominator.
        - delivery_unknown is excluded from the success-rate denominator (tracked separately).
        - success_rate = ((simulated + sent) / attempted * 100.0) if attempted > 0 else 0.0
        - Zero synthetic or artificial metrics.
    """
    with get_db_connection(db_path) as conn:
        # 1. Total contacts
        total_contacts = conn.execute("SELECT count(*) FROM contacts;").fetchone()[0]

        # 2. Reminder status counts
        cursor = conn.execute("SELECT status, count(*) AS cnt FROM reminders GROUP BY status;")
        status_map = {row["status"]: row["cnt"] for row in cursor.fetchall()}
        total_reminders = conn.execute("SELECT count(*) FROM reminders;").fetchone()[0]

        # 3. Department breakdown
        dept_cursor = conn.execute(
            """
            SELECT coalesce(c.department, 'Unassigned') AS dept, count(r.reminder_id) AS cnt
            FROM reminders r
            LEFT JOIN contacts c ON r.contact_id = c.contact_id
            GROUP BY dept
            ORDER BY cnt DESC, dept ASC;
            """
        )
        department_counts = {row["dept"]: row["cnt"] for row in dept_cursor.fetchall()}

        # 4. Template key breakdown
        tmpl_cursor = conn.execute(
            "SELECT template_key, count(*) AS cnt FROM reminders GROUP BY template_key ORDER BY cnt DESC, template_key ASC;"
        )
        template_counts = {row["template_key"]: row["cnt"] for row in tmpl_cursor.fetchall()}

    pending = status_map.get("pending", 0)
    ready = status_map.get("ready", 0)
    processing = status_map.get("processing", 0)
    simulated = status_map.get("simulated", 0)
    smtp_accepted = status_map.get("sent", 0)
    failed = status_map.get("failed", 0)
    delivery_unknown = status_map.get("delivery_unknown", 0)

    # Invariant: Attempted excludes pending, ready, processing, and delivery_unknown
    attempted = simulated + smtp_accepted + failed
    success_rate = ((simulated + smtp_accepted) / attempted * 100.0) if attempted > 0 else 0.0

    return {
        "total_contacts": total_contacts,
        "total_reminders": total_reminders,
        "pending": pending,
        "ready": ready,
        "processing": processing,
        "simulated": simulated,
        "smtp_accepted": smtp_accepted,
        "failed": failed,
        "delivery_unknown": delivery_unknown,
        "attempted": attempted,
        "success_rate": round(success_rate, 1),
        "status_counts": {
            "pending": pending,
            "ready": ready,
            "processing": processing,
            "simulated": simulated,
            "sent (SMTP accepted)": smtp_accepted,
            "failed": failed,
            "delivery_unknown": delivery_unknown,
        },
        "department_counts": department_counts,
        "template_counts": template_counts,
    }


# =====================================================================
# Phase 11 Dedicated Analytical Metrics
# =====================================================================

def get_reminder_status_metrics(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    as_of: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Analyzes reminder records across all 7 statuses, distinguishing overdue from upcoming.
    
    Overdue Definition:
        due_at <= as_of (UTC) AND status IN ('pending', 'ready').
        Reminders that have already been simulated or sent are dispatched, not overdue.
        
    Upcoming Definition:
        due_at > as_of (UTC).
    """
    now_utc = as_of if as_of is not None else datetime.now(timezone.utc)
    now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_db_connection(db_path) as conn:
        total_reminders = conn.execute("SELECT count(*) FROM reminders;").fetchone()[0]
        status_rows = conn.execute("SELECT status, count(*) AS cnt FROM reminders GROUP BY status;").fetchall()
        status_counts = {r["status"]: r["cnt"] for r in status_rows}

        # Actionable overdue reminders (due_at <= now AND status in actionable states)
        overdue_row = conn.execute(
            "SELECT count(*) FROM reminders WHERE due_at <= ? AND status IN ('pending', 'ready');",
            [now_iso],
        ).fetchone()
        overdue_count = overdue_row[0] if overdue_row else 0

        # Actionable upcoming reminders: ONLY pending or ready records with due_at > now
        # Strictly excludes completed or terminal statuses (simulated, sent, failed, delivery_unknown)
        upcoming_row = conn.execute(
            "SELECT count(*) FROM reminders WHERE due_at > ? AND status IN ('pending', 'ready');",
            [now_iso],
        ).fetchone()
        upcoming_count = upcoming_row[0] if upcoming_row else 0

        # Total future reminders (all statuses, including terminal/completed)
        future_total_row = conn.execute(
            "SELECT count(*) FROM reminders WHERE due_at > ?;",
            [now_iso],
        ).fetchone()
        future_total = future_total_row[0] if future_total_row else 0

        # Total historical past-due reminders (all statuses, including dispatched)
        past_due_total = conn.execute(
            "SELECT count(*) FROM reminders WHERE due_at <= ?;",
            [now_iso],
        ).fetchone()[0]

    pending = status_counts.get("pending", 0)
    ready = status_counts.get("ready", 0)
    processing = status_counts.get("processing", 0)
    simulated = status_counts.get("simulated", 0)
    sent = status_counts.get("sent", 0)
    failed = status_counts.get("failed", 0)
    delivery_unknown = status_counts.get("delivery_unknown", 0)

    overdue_pct = round((overdue_count / total_reminders * 100.0), 1) if total_reminders > 0 else 0.0
    upcoming_pct = round((upcoming_count / total_reminders * 100.0), 1) if total_reminders > 0 else 0.0

    return {
        "as_of_utc": now_iso,
        "total_reminders": total_reminders,
        "pending": pending,
        "ready": ready,
        "processing": processing,
        "simulated": simulated,
        "sent": sent,
        "failed": failed,
        "delivery_unknown": delivery_unknown,
        "overdue_count": overdue_count,
        "overdue_pct": overdue_pct,
        "upcoming_count": upcoming_count,
        "upcoming_actionable_count": upcoming_count,
        "future_total": future_total,
        "upcoming_pct": upcoming_pct,
        "past_due_total": past_due_total,
        "all_statuses": {
            "pending": pending,
            "ready": ready,
            "processing": processing,
            "simulated": simulated,
            "sent": sent,
            "failed": failed,
            "delivery_unknown": delivery_unknown,
        },
    }


def get_dispatch_performance_metrics(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Computes email dispatch KPIs strictly according to Phase 9 & Phase 10 definitions.
    
    Formula:
        Attempted = Simulated + Sent (SMTP Accepted) + Failed
        Success Rate = (Simulated + Sent) / Attempted * 100.0
        
    Strict Exclusions:
        - Excludes pending, ready, and processing from attempted.
        - Excludes delivery_unknown from success-rate denominator.
        - Labels simulated separately from actual SMTP-accepted dispatches.
        - Safely handles attempted == 0 by setting success_rate to None (avoiding false 0% failure alarms).
    """
    with get_db_connection(db_path) as conn:
        status_rows = conn.execute("SELECT status, count(*) AS cnt FROM reminders GROUP BY status;").fetchall()
        status_map = {r["status"]: r["cnt"] for r in status_rows}

    simulated = status_map.get("simulated", 0)
    smtp_accepted = status_map.get("sent", 0)
    failed = status_map.get("failed", 0)
    delivery_unknown = status_map.get("delivery_unknown", 0)

    attempted = simulated + smtp_accepted + failed
    has_attempted = attempted > 0
    success_rate = round(((simulated + smtp_accepted) / attempted * 100.0), 1) if has_attempted else None

    return {
        "simulated": simulated,
        "smtp_accepted": smtp_accepted,
        "failed": failed,
        "delivery_unknown": delivery_unknown,
        "attempted": attempted,
        "has_attempted": has_attempted,
        "success_rate": success_rate,
        "formatted_success_rate": f"{success_rate:.1f}%" if success_rate is not None else "N/A (0 attempts)",
        "smtp_delivery_clarification": (
            "SMTP acceptance confirms delivery handover to the configured mail transfer agent (MTA), "
            "not verified receipt by the end-user mailbox."
        ),
    }


def get_time_distribution_metrics(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    as_of: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Analyzes temporal distribution of reminders across days, weeks, months, and lead-time buckets."""
    now_utc = as_of if as_of is not None else datetime.now(timezone.utc)
    now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_db_connection(db_path) as conn:
        # Group by due_date (YYYY-MM-DD)
        date_rows = conn.execute(
            """
            SELECT substr(due_at, 1, 10) AS due_date, count(*) AS cnt
            FROM reminders
            GROUP BY due_date
            ORDER BY due_date ASC;
            """
        ).fetchall()
        by_day = {r["due_date"]: r["cnt"] for r in date_rows}

        # Group by due_month (YYYY-MM)
        month_rows = conn.execute(
            """
            SELECT substr(due_at, 1, 7) AS due_month, count(*) AS cnt
            FROM reminders
            GROUP BY due_month
            ORDER BY due_month ASC;
            """
        ).fetchall()
        by_month = {r["due_month"]: r["cnt"] for r in month_rows}

        # Lead time buckets relative to now_utc
        in_24h = (now_utc + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        in_7d = (now_utc + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        in_30d = (now_utc + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

        due_next_24h = conn.execute(
            "SELECT count(*) FROM reminders WHERE due_at > ? AND due_at <= ? AND status IN ('pending', 'ready');",
            [now_iso, in_24h],
        ).fetchone()[0]

        due_next_7d = conn.execute(
            "SELECT count(*) FROM reminders WHERE due_at > ? AND due_at <= ? AND status IN ('pending', 'ready');",
            [now_iso, in_7d],
        ).fetchone()[0]

        due_next_30d = conn.execute(
            "SELECT count(*) FROM reminders WHERE due_at > ? AND due_at <= ? AND status IN ('pending', 'ready');",
            [now_iso, in_30d],
        ).fetchone()[0]

        due_beyond_30d = conn.execute(
            "SELECT count(*) FROM reminders WHERE due_at > ? AND status IN ('pending', 'ready');",
            [in_30d],
        ).fetchone()[0]

        # Upcoming actionable reminders by day
        upcoming_date_rows = conn.execute(
            """
            SELECT substr(due_at, 1, 10) AS due_date, count(*) AS cnt
            FROM reminders
            WHERE due_at > ? AND status IN ('pending', 'ready')
            GROUP BY due_date
            ORDER BY due_date ASC;
            """,
            [now_iso],
        ).fetchall()
        upcoming_by_day = {r["due_date"]: r["cnt"] for r in upcoming_date_rows}

        # Upcoming actionable reminders by month
        upcoming_month_rows = conn.execute(
            """
            SELECT substr(due_at, 1, 7) AS due_month, count(*) AS cnt
            FROM reminders
            WHERE due_at > ? AND status IN ('pending', 'ready')
            GROUP BY due_month
            ORDER BY due_month ASC;
            """,
            [now_iso],
        ).fetchall()
        upcoming_by_month = {r["due_month"]: r["cnt"] for r in upcoming_month_rows}

        total_upcoming_actionable = conn.execute(
            "SELECT count(*) FROM reminders WHERE due_at > ? AND status IN ('pending', 'ready');",
            [now_iso],
        ).fetchone()[0]

        # Activity log event volume by date
        log_date_rows = conn.execute(
            """
            SELECT substr(timestamp, 1, 10) AS log_date, count(*) AS cnt
            FROM activity_logs
            GROUP BY log_date
            ORDER BY log_date ASC;
            """
        ).fetchall()
        activity_by_day = {r["log_date"]: r["cnt"] for r in log_date_rows}

    return {
        "as_of_utc": now_iso,
        "by_day": by_day,
        "by_month": by_month,
        "upcoming_by_day": upcoming_by_day,
        "upcoming_by_month": upcoming_by_month,
        "total_upcoming_actionable": total_upcoming_actionable,
        "lead_time_buckets": {
            "due_next_24h": due_next_24h,
            "due_next_7d": due_next_7d,
            "due_next_30d": due_next_30d,
            "due_beyond_30d": due_beyond_30d,
        },
        "activity_by_day": activity_by_day,
    }


def get_department_and_company_metrics(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Analyzes reminder distributions, workload concentration, and dispatch outcomes across departments and companies."""
    with get_db_connection(db_path) as conn:
        total_reminders = conn.execute("SELECT count(*) FROM reminders;").fetchone()[0]
        total_contacts = conn.execute("SELECT count(*) FROM contacts;").fetchone()[0]

        dept_rows = conn.execute(
            """
            SELECT coalesce(c.department, 'Unassigned') AS dept, count(r.reminder_id) AS cnt
            FROM reminders r
            LEFT JOIN contacts c ON r.contact_id = c.contact_id
            GROUP BY dept
            ORDER BY cnt DESC, dept ASC;
            """
        ).fetchall()
        dept_counts = {r["dept"]: r["cnt"] for r in dept_rows}

        company_rows = conn.execute(
            """
            SELECT coalesce(c.company, 'Unassigned') AS comp, count(r.reminder_id) AS cnt
            FROM reminders r
            LEFT JOIN contacts c ON r.contact_id = c.contact_id
            GROUP BY comp
            ORDER BY cnt DESC, comp ASC;
            """
        ).fetchall()
        company_counts = {r["comp"]: r["cnt"] for r in company_rows}

        # Outcomes by department
        outcomes_rows = conn.execute(
            """
            SELECT coalesce(c.department, 'Unassigned') AS dept, r.status, count(*) AS cnt
            FROM reminders r
            LEFT JOIN contacts c ON r.contact_id = c.contact_id
            GROUP BY dept, r.status;
            """
        ).fetchall()
        dept_outcomes: Dict[str, Dict[str, int]] = {}
        for r in outcomes_rows:
            dept = r["dept"]
            dept_outcomes.setdefault(dept, {})[r["status"]] = r["cnt"]

    # Concentration analysis
    top_dept = next(iter(dept_counts.items()), ("None", 0))
    top_company = next(iter(company_counts.items()), ("None", 0))

    top_dept_pct = round((top_dept[1] / total_reminders * 100.0), 1) if total_reminders > 0 else 0.0
    top_company_pct = round((top_company[1] / total_reminders * 100.0), 1) if total_reminders > 0 else 0.0

    # Small sample indicator (N < 30)
    is_small_sample = total_reminders < 30 or total_contacts < 30

    return {
        "total_contacts": total_contacts,
        "total_reminders": total_reminders,
        "department_counts": dept_counts,
        "company_counts": company_counts,
        "dept_outcomes": dept_outcomes,
        "top_department": top_dept[0],
        "top_department_count": top_dept[1],
        "top_department_pct": top_dept_pct,
        "top_company": top_company[0],
        "top_company_count": top_company[1],
        "top_company_pct": top_company_pct,
        "is_small_sample": is_small_sample,
        "sample_size_caveat": (
            f"Dataset contains {total_reminders} reminders across {total_contacts} contacts. "
            "Metrics reflect operational workload distribution rather than statistically generalizable findings."
        ) if is_small_sample else "",
    }


def get_category_and_template_metrics(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Analyzes reminders by functional category (reminder_type) and template key."""
    with get_db_connection(db_path) as conn:
        total_reminders = conn.execute("SELECT count(*) FROM reminders;").fetchone()[0]

        cat_rows = conn.execute(
            """
            SELECT coalesce(reminder_type, 'unclassified') AS cat, count(*) AS cnt
            FROM reminders
            GROUP BY cat
            ORDER BY cnt DESC, cat ASC;
            """
        ).fetchall()
        category_counts = {r["cat"]: r["cnt"] for r in cat_rows}

        tmpl_rows = conn.execute(
            """
            SELECT coalesce(template_key, 'unassigned') AS tmpl, count(*) AS cnt
            FROM reminders
            GROUP BY tmpl
            ORDER BY cnt DESC, tmpl ASC;
            """
        ).fetchall()
        template_counts = {r["tmpl"]: r["cnt"] for r in tmpl_rows}

        outcomes_rows = conn.execute(
            """
            SELECT coalesce(reminder_type, 'unclassified') AS cat, status, count(*) AS cnt
            FROM reminders
            GROUP BY cat, status;
            """
        ).fetchall()
        category_outcomes: Dict[str, Dict[str, int]] = {}
        for r in outcomes_rows:
            cat = r["cat"]
            category_outcomes.setdefault(cat, {})[r["status"]] = r["cnt"]

    top_cat = next(iter(category_counts.items()), ("None", 0))
    top_cat_pct = round((top_cat[1] / total_reminders * 100.0), 1) if total_reminders > 0 else 0.0

    return {
        "total_reminders": total_reminders,
        "category_counts": category_counts,
        "template_counts": template_counts,
        "category_outcomes": category_outcomes,
        "top_category": top_cat[0],
        "top_category_count": top_cat[1],
        "top_category_pct": top_cat_pct,
    }


def get_operational_workload_metrics(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    as_of: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Identifies operational bottlenecks, overdue items, and delivery-unknown review cases."""
    now_utc = as_of if as_of is not None else datetime.now(timezone.utc)
    now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_db_connection(db_path) as conn:
        # Overdue reminder records
        overdue_rows = conn.execute(
            """
            SELECT reminder_id, contact_id, reminder_type, due_at, status
            FROM reminders
            WHERE due_at <= ? AND status IN ('pending', 'ready')
            ORDER BY due_at ASC;
            """,
            [now_iso],
        ).fetchall()
        overdue_items = [dict(r) for r in overdue_rows]

        # Delivery unknown records requiring manual reconciliation
        unknown_rows = conn.execute(
            """
            SELECT reminder_id, contact_id, template_key, updated_at, dispatch_error
            FROM reminders
            WHERE status = 'delivery_unknown'
            ORDER BY updated_at DESC;
            """
        ).fetchall()
        unknown_items = [dict(r) for r in unknown_rows]

        # Processing records (in-flight or stale)
        processing_rows = conn.execute(
            """
            SELECT reminder_id, contact_id, template_key, updated_at
            FROM reminders
            WHERE status = 'processing'
            ORDER BY updated_at DESC;
            """
        ).fetchall()
        processing_items = [dict(r) for r in processing_rows]

        # Peak due date workload
        peak_row = conn.execute(
            """
            SELECT substr(due_at, 1, 10) AS due_date, count(*) AS cnt
            FROM reminders
            GROUP BY due_date
            ORDER BY cnt DESC, due_date ASC
            LIMIT 1;
            """
        ).fetchone()
        peak_date = peak_row["due_date"] if peak_row else "None"
        peak_count = peak_row["cnt"] if peak_row else 0

        # Contact mapping integrity: reminders with missing contact references
        orphan_count = conn.execute(
            """
            SELECT count(*) FROM reminders r
            LEFT JOIN contacts c ON r.contact_id = c.contact_id
            WHERE c.contact_id IS NULL;
            """
        ).fetchone()[0]

    return {
        "as_of_utc": now_iso,
        "overdue_count": len(overdue_items),
        "overdue_items": overdue_items,
        "delivery_unknown_count": len(unknown_items),
        "delivery_unknown_items": unknown_items,
        "processing_count": len(processing_items),
        "processing_items": processing_items,
        "peak_due_date": peak_date,
        "peak_due_count": peak_count,
        "orphan_reminder_count": orphan_count,
    }


# =====================================================================
# Interpretation Engine
# =====================================================================

def generate_system_interpretations(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    as_of: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Generates concise, factual, data-grounded operational interpretations from actual database records.
    
    Guarantees:
        - 100% grounded in actual calculated metrics; zero synthetic or invented findings.
        - Reports 'insufficient data' when datasets are empty.
        - Never claims causation from correlation or distribution.
        - Never misinterprets pending future reminders as failures.
        - Accurately reports zero dispatches without generating false 0% failure alarms.
    """
    status_m = get_reminder_status_metrics(db_path, as_of=as_of)
    perf_m = get_dispatch_performance_metrics(db_path)
    dept_m = get_department_and_company_metrics(db_path)
    cat_m = get_category_and_template_metrics(db_path)
    time_m = get_time_distribution_metrics(db_path, as_of=as_of)
    op_m = get_operational_workload_metrics(db_path, as_of=as_of)

    total_r = status_m["total_reminders"]
    total_c = dept_m["total_contacts"]

    # 1. Empty Dataset Guard
    if total_r == 0:
        return [
            {
                "category": "Dataset Status",
                "title": "Insufficient Data for Analysis",
                "finding": "The database contains zero reminder records. Analytical metrics and interpretations cannot be computed.",
                "evidence": "Total Reminders = 0, Total Contacts = " + str(total_c),
                "badge": "Insufficient Data",
                "severity": "neutral",
                "actionable": "Import reminder records from CSV or synchronize sample data via Settings.",
            }
        ]

    interpretations: List[Dict[str, Any]] = []

    # 2. Workload & Department Concentration Interpretation
    top_dept = dept_m["top_department"]
    top_dept_cnt = dept_m["top_department_count"]
    top_dept_pct = dept_m["top_department_pct"]
    dept_finding = (
        f"The '{top_dept}' department holds the highest reminder workload, "
        f"accounting for {top_dept_cnt} of {total_r} reminders ({top_dept_pct}%)."
    )
    if dept_m["is_small_sample"]:
        dept_finding += f" (Note: Sample size N={total_r} reflects operational workload concentration rather than statistical significance)."

    dept_evidence = ", ".join([f"{d}: {c}" for d, c in list(dept_m["department_counts"].items())[:4]])
    interpretations.append({
        "category": "Workload Concentration",
        "title": "Department Workload Concentration",
        "finding": dept_finding,
        "evidence": f"Department Breakdown: {dept_evidence}",
        "badge": f"{top_dept} ({top_dept_pct}%)",
        "severity": "info",
        "actionable": "Monitor distribution to prevent single-department notification bottlenecks.",
    })

    # 3. Reminder Category & Template Interpretation
    top_cat = cat_m["top_category"]
    top_cat_cnt = cat_m["top_category_count"]
    top_cat_pct = cat_m["top_category_pct"]
    cat_finding = (
        f"'{top_cat.title()}' reminders are the most common functional category, "
        f"comprising {top_cat_cnt} of {total_r} reminders ({top_cat_pct}%)."
    )
    cat_evidence = ", ".join([f"{k}: {v}" for k, v in cat_m["category_counts"].items()])
    interpretations.append({
        "category": "Category Distribution",
        "title": "Primary Reminder Category",
        "finding": cat_finding,
        "evidence": f"Category Breakdown: {cat_evidence}",
        "badge": f"{top_cat.title()} ({top_cat_pct}%)",
        "severity": "info",
        "actionable": f"Ensure templates associated with '{top_cat}' remain up to date.",
    })

    # 4. Schedule & Due Date Analysis
    overdue_cnt = status_m["overdue_count"]
    upcoming_cnt = status_m["upcoming_count"]
    lead_buckets = time_m["lead_time_buckets"]
    
    if overdue_cnt == 0:
        time_finding = (
            f"Zero reminders are overdue relative to current UTC time. All {upcoming_cnt} reminders "
            f"are scheduled for future dispatch"
        )
        if upcoming_cnt > 0 and lead_buckets["due_beyond_30d"] == upcoming_cnt:
            time_finding += f" (100% of upcoming actionable reminders due beyond 30 days, e.g., in {list(time_m['by_month'].keys())[0] if time_m['by_month'] else 'future dates'})."
        else:
            time_finding += f" ({lead_buckets['due_next_7d']} due in next 7 days, {lead_buckets['due_next_30d']} due in next 30 days)."
        time_severity = "success"
        time_badge = "0 Overdue (100% Upcoming)"
    else:
        time_finding = (
            f"{overdue_cnt} of {total_r} reminders ({status_m['overdue_pct']}%) are currently overdue "
            "and pending dispatch preparation."
        )
        time_severity = "warning"
        time_badge = f"{overdue_cnt} Overdue"

    interpretations.append({
        "category": "Schedule & Timelines",
        "title": "Due Date & Lead-Time Analysis",
        "finding": time_finding,
        "evidence": (
            f"Overdue: {overdue_cnt}, Upcoming Actionable: {upcoming_cnt}, "
            f"Next 24h: {lead_buckets['due_next_24h']}, Next 7d: {lead_buckets['due_next_7d']}, Beyond 30d: {lead_buckets['due_beyond_30d']}"
        ),
        "badge": time_badge,
        "severity": time_severity,
        "actionable": "Run one-time scheduler check on the Reminders page if overdue reminders are present." if overdue_cnt > 0 else "No immediate dispatch required for future reminders.",
    })

    # 5. Dispatch Performance & Handover Reliability
    attempted = perf_m["attempted"]
    simulated = perf_m["simulated"]
    sent = perf_m["smtp_accepted"]
    failed = perf_m["failed"]
    
    if not perf_m["has_attempted"]:
        actionable_pending = status_m['pending'] + status_m['ready']
        dispatch_finding = (
            f"Zero dispatches have been attempted yet (0 simulated, 0 SMTP sent, 0 failed). "
            f"All {actionable_pending} non-dispatched reminders remain in the pipeline awaiting their scheduled due dates. "
            "Success rate is marked as N/A until dispatches are executed."
        )
        dispatch_severity = "neutral"
        dispatch_badge = "No Dispatches Yet (N/A)"
    else:
        rate = perf_m["success_rate"]
        dispatch_finding = (
            f"A total of {attempted} dispatches have been attempted with an operational success rate of {rate}%. "
            f"Breakdown: {simulated} simulated sandbox dispatches, {sent} live SMTP handovers, and {failed} failed dispatches. "
            f"{perf_m['smtp_delivery_clarification']}"
        )
        dispatch_severity = "success" if rate >= 90.0 else ("warning" if rate >= 70.0 else "error")
        dispatch_badge = f"{rate}% Success Rate ({attempted} attempts)"

    interpretations.append({
        "category": "Dispatch Performance",
        "title": "Email Dispatch Execution & Handover",
        "finding": dispatch_finding,
        "evidence": f"Attempted: {attempted} (Simulated: {simulated}, Sent: {sent}, Failed: {failed})",
        "badge": dispatch_badge,
        "severity": dispatch_severity,
        "actionable": "Execute dry-run simulation or authorized live send when reminders become due.",
    })

    # 6. Operational Health & Alert Review
    unknown_cnt = op_m["delivery_unknown_count"]
    proc_cnt = op_m["processing_count"]
    orphan_cnt = op_m["orphan_reminder_count"]

    alerts = []
    if unknown_cnt > 0:
        alerts.append(f"{unknown_cnt} record(s) in 'delivery_unknown' require manual operator reconciliation.")
    if proc_cnt > 0:
        alerts.append(f"{proc_cnt} record(s) currently in 'processing' state.")
    if orphan_cnt > 0:
        alerts.append(f"{orphan_cnt} reminder(s) have missing contact associations.")

    if alerts:
        health_finding = "Operational Attention Required: " + " ".join(alerts)
        health_severity = "warning"
        health_badge = "Attention Required"
    else:
        health_finding = (
            "System Integrity Verified: All pipeline queues are operating normally. "
            "0 ambiguous delivery-unknown records require review, 0 records are stranded in processing, "
            "and 100% of reminders have valid contact references."
        )
        health_severity = "success"
        health_badge = "All Systems Healthy"

    interpretations.append({
        "category": "Operational Integrity",
        "title": "System Health & Integrity Status",
        "finding": health_finding,
        "evidence": f"Delivery Unknown: {unknown_cnt}, In-Flight Processing: {proc_cnt}, Orphan Reminders: {orphan_cnt}",
        "badge": health_badge,
        "severity": health_severity,
        "actionable": "Inspect Email History for delivery_unknown details if alerts are active." if alerts else "No operator intervention required.",
    })

    return interpretations


# =====================================================================
# Existing Dataframe Retrieval Helpers (Phase 10 Intact)
# =====================================================================

def get_all_contacts_df(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    search_query: Optional[str] = None,
    department: Optional[str] = None,
    company: Optional[str] = None,
) -> pd.DataFrame:
    """Retrieves contacts from SQLite as a pandas DataFrame with parameterized filtering."""
    conditions: List[str] = []
    params: List[Any] = []

    if search_query and search_query.strip():
        q = f"%{search_query.strip()}%"
        conditions.append("(first_name LIKE ? OR last_name LIKE ? OR email LIKE ?)")
        params.extend([q, q, q])

    if department and department != "All":
        conditions.append("department = ?")
        params.append(department.strip())

    if company and company != "All":
        conditions.append("company = ?")
        params.append(company.strip())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT 
            contact_id AS "Contact ID",
            first_name || ' ' || last_name AS "Name",
            email AS "Email",
            department AS "Department",
            company AS "Company",
            created_at AS "Created At"
        FROM contacts
        {where_clause}
        ORDER BY contact_id ASC;
    """

    with get_db_connection(db_path) as conn:
        df = pd.read_sql_query(query, conn, params=params)
    return df


def get_all_reminders_df(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    status: Optional[str] = None,
    template_key: Optional[str] = None,
    search_query: Optional[str] = None,
) -> pd.DataFrame:
    """Retrieves reminders joined with contact info as a pandas DataFrame with parameterized filtering."""
    conditions: List[str] = []
    params: List[Any] = []

    if status and status != "All":
        conditions.append("r.status = ?")
        params.append(status.strip())

    if template_key and template_key != "All":
        conditions.append("r.template_key = ?")
        params.append(template_key.strip())

    if search_query and search_query.strip():
        q = f"%{search_query.strip()}%"
        conditions.append("(r.reminder_id LIKE ? OR r.reference_id LIKE ? OR c.first_name LIKE ? OR c.last_name LIKE ?)")
        params.extend([q, q, q, q])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT 
            r.reminder_id AS "Reminder ID",
            r.contact_id AS "Contact ID",
            coalesce(c.first_name || ' ' || c.last_name, 'Unknown') AS "Recipient Name",
            coalesce(c.email, '') AS "Email",
            r.reminder_type AS "Type",
            r.template_key AS "Template",
            r.due_at AS "Due At (UTC)",
            r.status AS "Status",
            r.reference_id AS "Reference ID",
            r.notes AS "Notes",
            coalesce(r.dispatch_error, '') AS "Error / Notes",
            r.updated_at AS "Last Updated"
        FROM reminders r
        LEFT JOIN contacts c ON r.contact_id = c.contact_id
        {where_clause}
        ORDER BY r.due_at ASC, r.reminder_id ASC;
    """

    with get_db_connection(db_path) as conn:
        df = pd.read_sql_query(query, conn, params=params)
    return df


def get_email_history_df(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    status: Optional[str] = None,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None,
    search_query: Optional[str] = None,
) -> pd.DataFrame:
    """Retrieves actual email dispatch records (excluding pending, ready, and processing)."""
    conditions: List[str] = [
        "r.status IN ('simulated', 'sent', 'failed', 'delivery_unknown')"
    ]
    params: List[Any] = []

    if status and status != "All":
        conditions.append("r.status = ?")
        params.append(status.strip())

    if start_date:
        s_str = start_date.isoformat() if isinstance(start_date, datetime) else str(start_date).strip()
        if len(s_str) == 10 and "T" not in s_str:
            s_str += "T00:00:00Z"
        conditions.append("r.due_at >= ?")
        params.append(s_str)

    if end_date:
        e_str = end_date.isoformat() if isinstance(end_date, datetime) else str(end_date).strip()
        if len(e_str) == 10 and "T" not in e_str:
            e_str += "T23:59:59Z"
        conditions.append("r.due_at <= ?")
        params.append(e_str)

    if search_query and search_query.strip():
        q = f"%{search_query.strip()}%"
        conditions.append("(r.reminder_id LIKE ? OR coalesce(p.recipient_email, c.email) LIKE ? OR coalesce(p.subject, '') LIKE ?)")
        params.extend([q, q, q])

    where_clause = f"WHERE {' AND '.join(conditions)}"

    query = f"""
        SELECT 
            r.reminder_id AS "Reminder ID",
            coalesce(c.first_name || ' ' || c.last_name, 'Unknown') AS "Recipient",
            coalesce(p.recipient_email, c.email, '') AS "Email",
            r.template_key AS "Template",
            coalesce(p.subject, '') AS "Subject",
            r.status AS "Dispatch Status",
            coalesce(p.prepared_at, '') AS "Prepared At",
            r.updated_at AS "Dispatched At",
            coalesce(r.dispatch_error, '') AS "Failure Reason"
        FROM reminders r
        LEFT JOIN contacts c ON r.contact_id = c.contact_id
        LEFT JOIN prepared_emails p ON r.reminder_id = p.reminder_id
        {where_clause}
        ORDER BY r.updated_at DESC, r.reminder_id ASC;
    """

    with get_db_connection(db_path) as conn:
        df = pd.read_sql_query(query, conn, params=params)
    return df


def get_activity_timeline_df(
    db_path: Union[Path, str] = DEFAULT_DB_PATH,
    limit: int = 50,
) -> pd.DataFrame:
    """Retrieves recent audit activity events for display in timeline and history views."""
    query = f"""
        SELECT 
            log_id AS "Log ID",
            timestamp AS "Timestamp (UTC)",
            event_type AS "Event Type",
            severity AS "Severity",
            status AS "Status",
            message AS "Message",
            reminder_id AS "Reminder ID",
            contact_id AS "Contact ID"
        FROM activity_logs
        ORDER BY timestamp DESC, log_id DESC
        LIMIT {int(limit)};
    """
    with get_db_connection(db_path) as conn:
        df = pd.read_sql_query(query, conn)
    return df
