"""
api/reports/router.py — Phase 8: Reporting endpoints.

All 7 endpoints follow the same pattern:
  1. Parse query params (time range + optional filters)
  2. Delegate to ReportService
  3. Return result dict directly

Router is a thin HTTP boundary — no SQL, no business logic.

## Time range query params (shared by all endpoints)

  ?period=1d|7d|30d|90d       Relative range shorthand
  ?since=<ISO-8601>            Explicit start (inclusive)
  ?until=<ISO-8601>            Explicit end   (exclusive)

  Precedence: since+until > period > default(7d)
  Maximum range: 90 days (REPORT_MAX_RANGE_DAYS)

## Response envelope (all endpoints)

  {
    "since":       "2026-07-04T00:00:00+00:00",
    "until":       "2026-08-10T00:00:00+00:00",
    "granularity": "hour" | "day" | "week" | null,
    "data":        [...]
  }
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentUser
from app.db.session import get_db
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


# ── Shared time-range resolution (per request) ────────────────────────────────

def _resolve(
    since: Optional[datetime],
    until: Optional[datetime],
    period: Optional[str],
):
    try:
        return ReportService.resolve_time_range(since, until, period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ── Operational reports ───────────────────────────────────────────────────────

@router.get("/runs")
def runs_report(
    period: Optional[str] = Query(None, description="1d|7d|30d|90d"),
    since:  Optional[datetime] = Query(None),
    until:  Optional[datetime] = Query(None),
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """
    Run volume summary for the time window.

    Returns total + by_status + by_priority breakdown and a time-bucketed
    trend line. Granularity is adaptive (hour/day/week).
    """
    s, u = _resolve(since, until, period)
    return ReportService.runs_report(db, current_user.org_id, s, u)


@router.get("/queue")
def queue_report(
    period: Optional[str] = Query(None),
    since:  Optional[datetime] = Query(None),
    until:  Optional[datetime] = Query(None),
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """
    Queue wait-time statistics per adaptive time bucket.

    wait_seconds = started_at - triggered_at  (runs with non-null started_at only).
    Runs not yet dispatched are included in total_runs but excluded from wait averages.
    """
    s, u = _resolve(since, until, period)
    return ReportService.queue_report(db, current_user.org_id, s, u)


@router.get("/schedules")
def schedules_report(
    period: Optional[str] = Query(None),
    since:  Optional[datetime] = Query(None),
    until:  Optional[datetime] = Query(None),
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """
    Per-schedule trigger reliability (hit / skip / trigger_failed rates).

    Results are sorted by miss_rate descending — most unreliable schedules first.
    """
    s, u = _resolve(since, until, period)
    return ReportService.schedules_report(db, current_user.org_id, s, u)


@router.get("/agents")
def agents_report(
    period: Optional[str] = Query(None),
    since:  Optional[datetime] = Query(None),
    until:  Optional[datetime] = Query(None),
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """
    Agent execution statistics (run count + pass/fail + avg/p95 duration).

    NOTE: Does NOT include utilization_percent — insufficient heartbeat history
    for accurate uptime calculation. This reports execution volume only.
    """
    s, u = _resolve(since, until, period)
    return ReportService.agents_report(db, current_user.org_id, s, u)


# ── Quality reports ───────────────────────────────────────────────────────────

@router.get("/flakiness")
def flakiness_report(
    period:    Optional[str]   = Query(None),
    since:     Optional[datetime] = Query(None),
    until:     Optional[datetime] = Query(None),
    min_score: Optional[float] = Query(None, ge=0.0, le=1.0,
                                        description="Minimum flakiness score (0–1)"),
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """
    Flaky test leaderboard ranked by adjacent flip rate.

    Defaults: only test cases with >= 3 eligible terminal runs AND >= 1 flip.
    Optional: ?min_score=0.1 further filters by flakiness score (>= threshold).

    flakiness_score = flip_count / (eligible_runs - 1)   [0–1 float]
    """
    s, u = _resolve(since, until, period)
    return ReportService.flakiness_report(db, current_user.org_id, s, u, min_score)


@router.get("/pass-rate")
def pass_rate_report(
    period:       Optional[str]  = Query(None),
    since:        Optional[datetime] = Query(None),
    until:        Optional[datetime] = Query(None),
    test_case_id: Optional[UUID] = Query(None, description="Filter to a specific test case"),
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """
    Pass rate trend per adaptive time bucket.

    Only COMPLETED and FAILED runs count toward the pass rate.
    Optional: filter to a specific test case with ?test_case_id=<uuid>.
    """
    s, u = _resolve(since, until, period)
    return ReportService.pass_rate_report(db, current_user.org_id, s, u, test_case_id)


@router.get("/duration")
def duration_report(
    period:       Optional[str]  = Query(None),
    since:        Optional[datetime] = Query(None),
    until:        Optional[datetime] = Query(None),
    test_case_id: Optional[UUID] = Query(None, description="Filter to a specific test case"),
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """
    Execution duration trend (avg + p95) per adaptive time bucket.

    p95 uses nearest-rank method computed in Python for cross-DB compatibility.
    Only runs with both started_at and completed_at are included.
    Optional: filter to a specific test case with ?test_case_id=<uuid>.
    """
    s, u = _resolve(since, until, period)
    return ReportService.duration_report(db, current_user.org_id, s, u, test_case_id)
