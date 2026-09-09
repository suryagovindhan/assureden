"""
api/metrics/router.py — Phase 5 (refactored): thin HTTP boundary.

GET /metrics/dashboard

All computation and caching lives in MetricsService.
This module contains only the route handler and ACTIVE_TESTCASE_STATUSES
re-export (for tests that check the constant directly).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentUser
from app.db.session import get_db
from app.services.metrics_service import MetricsService, ACTIVE_TESTCASE_STATUSES  # noqa: F401

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/dashboard")
def dashboard_metrics(
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """
    Aggregate dashboard metrics for the current org.

    Response includes:
      runs            — total / queued / running / today / pass / fail
      queue_health    — queued count, oldest wait, average wait, longest wait
      agents          — total / online / idle / offline / running
      test_cases      — total / active
      scheduled_jobs  — total / enabled
      scheduler_health — enabled / disabled / due_now / missed_today
      recent_trend    — 7-day passed/failed per day

    Cached in-process for DASHBOARD_METRICS_CACHE_TTL_SECONDS (default 20s).
    """
    return MetricsService.get_dashboard_metrics(db, current_user.org_id)
