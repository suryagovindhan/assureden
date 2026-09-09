"""
services/metrics_service.py — Phase 5: Dashboard metrics service.

Architecture contract:
  Router  → calls MetricsService.get_dashboard_metrics() only
  Service → owns the TTL cache, all query logic, metric computation
  Repository → raw SQL (inlined here; no dedicated MetricsRepository needed
               because metrics queries are read-only aggregations)

Cache lives here, not in the router. Any future caller (internal report
generator, webhook batch, etc.) benefits automatically.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, cast
from sqlalchemy.orm import Session

try:
    from sqlalchemy import Date as SADate
except ImportError:
    from sqlalchemy.types import Date as SADate  # type: ignore

from app.core.cache import ttl_cache
from app.core.config import settings
from app.db.base import utcnow


# Test-case statuses considered "active" for operator metrics.
# Keep in sync with TestStatus in models/test_cases.py.
ACTIVE_TESTCASE_STATUSES = ("DRAFT", "READY")


class MetricsService:
    """
    Compute and cache dashboard metrics for an org.

    The TTL cache is keyed on (org_id_str) so that different orgs never
    share a cache entry. Exception safety: if any query raises, the exception
    propagates before the cache entry is written (never caches errors).
    """

    @staticmethod
    def get_dashboard_metrics(db: Session, org_id) -> dict:
        """
        Return the full dashboard payload for `org_id`.
        Cached for DASHBOARD_METRICS_CACHE_TTL_SECONDS (default 20 s).

        `org_id` may be a UUID object or str.
        """
        # Build the per-org cached function at call-time so the db session
        # is NOT part of the cache key (sessions are transient).
        org_id_str = str(org_id)

        @ttl_cache(ttl_seconds=settings.DASHBOARD_METRICS_CACHE_TTL_SECONDS)
        def _cached(oid: str) -> dict:
            return MetricsService._compute(db, oid)

        return _cached(org_id_str)

    # ── Core computation ──────────────────────────────────────────────────────

    @staticmethod
    def _compute(db: Session, org_id) -> dict:
        from app.models.executions import TestRun, RunStatus
        from app.models.foundation import Agent
        from app.models.test_cases import TestCase
        from app.models.schedules import ScheduledJob

        # ── Runs: total breakdown by status ──────────────────────────────────
        run_rows = (
            db.query(TestRun.status, func.count().label("cnt"))
            .filter(TestRun.org_id == org_id)
            .group_by(TestRun.status)
            .all()
        )
        runs_by_status = {r.status: r.cnt for r in run_rows}
        total_runs = sum(runs_by_status.values())
        queued  = runs_by_status.get(RunStatus.QUEUED, 0)
        running = (
            runs_by_status.get(RunStatus.RUNNING, 0)
            + runs_by_status.get(RunStatus.DISPATCHED, 0)
        )

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_rows = (
            db.query(TestRun.status, func.count().label("cnt"))
            .filter(TestRun.org_id == org_id, TestRun.triggered_at >= today_start)
            .group_by(TestRun.status)
            .all()
        )
        today_by_status = {r.status: r.cnt for r in today_rows}

        runs = {
            "total":        total_runs,
            "queued":       queued,
            "running":      running,
            "today":        sum(today_by_status.values()),
            "passed_today": today_by_status.get(RunStatus.COMPLETED, 0),
            "failed_today": today_by_status.get(RunStatus.FAILED, 0),
        }

        # ── Queue health ──────────────────────────────────────────────────────
        now = utcnow()
        queued_runs = (
            db.query(TestRun.triggered_at)
            .filter(TestRun.org_id == org_id, TestRun.status == RunStatus.QUEUED)
            .all()
        )
        if queued_runs:
            wait_times = [
                max(0, int((now - r.triggered_at).total_seconds()))
                for r in queued_runs
                if r.triggered_at
            ]
            queue_health = {
                "queued":              len(queued_runs),
                "oldest_wait_seconds": max(wait_times) if wait_times else 0,
                "average_wait_seconds": int(sum(wait_times) / len(wait_times)) if wait_times else 0,
                "longest_wait_seconds": max(wait_times) if wait_times else 0,
            }
        else:
            queue_health = {
                "queued": 0,
                "oldest_wait_seconds": 0,
                "average_wait_seconds": 0,
                "longest_wait_seconds": 0,
            }

        # ── Agents ────────────────────────────────────────────────────────────
        agent_rows = (
            db.query(Agent.status, func.count().label("cnt"))
            .filter(Agent.org_id == org_id, Agent.deleted_at.is_(None))
            .group_by(Agent.status)
            .all()
        )
        agents_by_status = {r.status: r.cnt for r in agent_rows}
        agents = {
            "total":   sum(agents_by_status.values()),
            "online":  agents_by_status.get("ONLINE", 0),
            "idle":    agents_by_status.get("IDLE", 0),
            "offline": agents_by_status.get("OFFLINE", 0),
            "running": agents_by_status.get("RUNNING", 0),
        }

        # ── Test cases ────────────────────────────────────────────────────────
        tc_total = (
            db.query(func.count(TestCase.id))
            .filter(TestCase.org_id == org_id, TestCase.deleted_at.is_(None))
            .scalar() or 0
        )
        tc_active = (
            db.query(func.count(TestCase.id))
            .filter(
                TestCase.org_id == org_id,
                TestCase.deleted_at.is_(None),
                TestCase.status.in_(ACTIVE_TESTCASE_STATUSES),
            )
            .scalar() or 0
        )
        test_cases = {"total": tc_total, "active": tc_active}

        # ── Scheduled jobs + scheduler health ────────────────────────────────
        sj_rows = (
            db.query(ScheduledJob.is_enabled, func.count().label("cnt"))
            .filter(ScheduledJob.org_id == org_id, ScheduledJob.deleted_at.is_(None))
            .group_by(ScheduledJob.is_enabled)
            .all()
        )
        sj_by_enabled = {r.is_enabled: r.cnt for r in sj_rows}
        sj_enabled  = sj_by_enabled.get(True, 0)
        sj_disabled = sj_by_enabled.get(False, 0)
        sj_total    = sj_enabled + sj_disabled

        due_now = (
            db.query(func.count(ScheduledJob.id))
            .filter(
                ScheduledJob.org_id == org_id,
                ScheduledJob.deleted_at.is_(None),
                ScheduledJob.is_enabled.is_(True),
                ScheduledJob.next_run_at <= now,
            )
            .scalar() or 0
        )

        from app.models.schedules import ScheduledRunHistory
        missed_today = (
            db.query(func.count(ScheduledRunHistory.id))
            .join(ScheduledJob, ScheduledRunHistory.job_id == ScheduledJob.id)
            .filter(
                ScheduledJob.org_id == org_id,
                ScheduledRunHistory.status == "SKIPPED",
                ScheduledRunHistory.triggered_at >= today_start,
            )
            .scalar() or 0
        )

        scheduled_jobs = {"total": sj_total, "enabled": sj_enabled}
        scheduler_health = {
            "enabled":       sj_enabled,
            "disabled":      sj_disabled,
            "due_now":       due_now,
            "missed_today":  missed_today,
        }

        # ── 7-day trend ───────────────────────────────────────────────────────
        since = utcnow() - timedelta(days=7)
        trend_rows = (
            db.query(
                cast(TestRun.triggered_at, SADate).label("date"),
                TestRun.status,
                func.count().label("cnt"),
            )
            .filter(TestRun.org_id == org_id, TestRun.triggered_at >= since)
            .group_by(cast(TestRun.triggered_at, SADate), TestRun.status)
            .all()
        )
        per_day: dict[str, dict] = {}
        for row in trend_rows:
            d = str(row.date)
            if d not in per_day:
                per_day[d] = {"date": d, "passed": 0, "failed": 0, "total": 0}
            per_day[d]["total"] += row.cnt
            if row.status == RunStatus.COMPLETED:
                per_day[d]["passed"] += row.cnt
            elif row.status == RunStatus.FAILED:
                per_day[d]["failed"] += row.cnt
        recent_trend = sorted(per_day.values(), key=lambda x: x["date"])

        return {
            "runs":             runs,
            "queue_health":     queue_health,
            "agents":           agents,
            "test_cases":       test_cases,
            "scheduled_jobs":   scheduled_jobs,
            "scheduler_health": scheduler_health,
            "recent_trend":     recent_trend,
        }
