"""
services/report_service.py — Phase 8: Reporting subsystem.

Architecture: ReportService is a collection of pure class methods.
No instantiation required. No mutable state.

All methods:
  - Accept a SQLAlchemy Session directly (passed by the router)
  - Return plain dicts (never ORM objects, never Pydantic models)
  - Are read-only — no INSERT / UPDATE / DELETE

## Time range contract

  resolve_time_range(since, until, period) -> (datetime, datetime)

  Precedence:
    1. since + until  → used exactly (after validation)
    2. period         → relative shorthand (1d/7d/30d/90d)
    3. default        → 7d

  Limits:
    - since must be < until
    - range may not exceed REPORT_MAX_RANGE_DAYS (90d)

## Adaptive granularity

  resolve_granularity(since, until) -> "hour" | "day" | "week"

    ≤ 48h  →  hour
    ≤ 31d  →  day
    > 31d  →  week

## Flakiness formula

  Adjacent flip rate = flip_count / (eligible_runs - 1)

  Only COMPLETED (pass) and FAILED (fail) terminal states count.
  ABORTED / CANCELLED / TIMED_OUT / QUEUED / RUNNING are excluded from
  the transition sequence.

  Default filter: eligible_runs >= FLAKINESS_MIN_ELIGIBLE_RUNS (3) AND flip_count >= 1
  Optional filter: flakiness_score >= min_score

## p95 computation

  percentile_95(values: list[float]) -> float

  Deterministic nearest-rank method:
    index = ceil(0.95 * len(values)) - 1
    Returns sorted[index]

  Single-element: p95 == avg (== the only value)
  Empty: returns 0.0

## Agent statistics

  Reports run count + passed + failed + avg/p95 duration per agent.
  Does NOT include a utilization_percent — insufficient heartbeat data.

## Response envelope (all endpoints)

  {
    "since":       "2026-07-04T00:00:00+00:00",
    "until":       "2026-08-10T00:00:00+00:00",
    "granularity": "day" | null,
    "data":        [...]
  }

  granularity is null for non-trend reports (flakiness, agents, runs summary).

## Queue wait definition

  wait_seconds = started_at - triggered_at  (for runs with non-null started_at)

  Runs still in QUEUED/DISPATCHED state (no started_at) are excluded from
  wait-time aggregation. The count of runs without a started_at is reported
  as "pending" so the caller knows the denominator is not the full queue.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

# Terminal states for flakiness computation
_PASS_STATUS = "COMPLETED"
_FAIL_STATUS = "FAILED"
_TERMINAL_FOR_FLAKINESS = {_PASS_STATUS, _FAIL_STATUS}

# Period shorthand → days
_PERIOD_DAYS = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}


# ── Shared helpers ────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc(dt: datetime) -> datetime:
    """Ensure a datetime is UTC-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ReportService:
    """Pure-class reporting service. No instantiation required."""

    # ── Time range & granularity resolution ───────────────────────────────────

    @staticmethod
    def resolve_time_range(
        since: Optional[datetime],
        until: Optional[datetime],
        period: Optional[str],
    ) -> tuple[datetime, datetime]:
        """
        Resolve the effective [since, until) window.

        Precedence: since+until > period > default(7d)

        Raises ValueError on:
          - since >= until
          - range exceeds REPORT_MAX_RANGE_DAYS
        """
        if since is not None and until is not None:
            since = _to_utc(since)
            until = _to_utc(until)
            if since >= until:
                raise ValueError("since must be before until")
            if (until - since).days > settings.REPORT_MAX_RANGE_DAYS:
                raise ValueError(
                    f"Time range exceeds maximum of {settings.REPORT_MAX_RANGE_DAYS} days"
                )
            return since, until

        days = _PERIOD_DAYS.get(period or "7d", 7)
        until_dt = _utcnow()
        since_dt = until_dt - timedelta(days=days)
        return since_dt, until_dt

    @staticmethod
    def resolve_granularity(since: datetime, until: datetime) -> str:
        """
        Return adaptive bucket size based on effective range.

          ≤ 48h  →  "hour"
          ≤ 31d  →  "day"
          > 31d  →  "week"
        """
        delta = until - since
        if delta <= timedelta(hours=48):
            return "hour"
        if delta <= timedelta(days=31):
            return "day"
        return "week"

    # ── p95 helper ────────────────────────────────────────────────────────────

    @staticmethod
    def percentile_95(values: list[float]) -> float:
        """
        Nearest-rank p95.

        index = ceil(0.95 * n) - 1   (0-based, clamped)

        Single element:  returns that element (== avg)
        Empty:           returns 0.0
        """
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        idx = max(0, math.ceil(0.95 * n) - 1)
        return sorted_vals[idx]

    # ── Runs report ───────────────────────────────────────────────────────────

    @classmethod
    def runs_report(
        cls,
        db: Session,
        org_id: UUID,
        since: datetime,
        until: datetime,
    ) -> dict:
        """
        Run volume summary for the given window.

        Returns: status breakdown + priority breakdown + trend buckets.
        Granularity is adaptive (used for the trend line only).
        """
        granularity = cls.resolve_granularity(since, until)
        trunc_fn = _trunc_fn(granularity, _dialect(db))

        # Status breakdown
        status_rows = db.execute(text("""
            SELECT status, COUNT(*) AS cnt
            FROM test_runs
            WHERE org_id = :org_id
              AND triggered_at >= :since
              AND triggered_at < :until
            GROUP BY status
        """), {"org_id": str(org_id), "since": since, "until": until}).fetchall()

        status_counts: dict[str, int] = {}
        for row in status_rows:
            status_counts[row[0]] = row[1]

        # Priority breakdown
        priority_rows = db.execute(text("""
            SELECT priority, COUNT(*) AS cnt
            FROM test_runs
            WHERE org_id = :org_id
              AND triggered_at >= :since
              AND triggered_at < :until
            GROUP BY priority
        """), {"org_id": str(org_id), "since": since, "until": until}).fetchall()

        priority_counts: dict[str, int] = {}
        for row in priority_rows:
            priority_counts[row[0]] = row[1]

        # Trend by bucket
        trend_rows = db.execute(text(f"""
            SELECT {trunc_fn('triggered_at')} AS bucket, COUNT(*) AS cnt
            FROM test_runs
            WHERE org_id = :org_id
              AND triggered_at >= :since
              AND triggered_at < :until
            GROUP BY bucket
            ORDER BY bucket ASC
        """), {"org_id": str(org_id), "since": since, "until": until}).fetchall()

        trend = [{"date": _fmt_dt(row[0]), "count": row[1]} for row in trend_rows]

        total = sum(status_counts.values())

        return {
            "since":       since.isoformat(),
            "until":       until.isoformat(),
            "granularity": granularity,
            "data": {
                "total":           total,
                "by_status":       status_counts,
                "by_priority":     priority_counts,
                "trend":           trend,
            },
        }

    # ── Queue report ──────────────────────────────────────────────────────────

    @classmethod
    def queue_report(
        cls,
        db: Session,
        org_id: UUID,
        since: datetime,
        until: datetime,
    ) -> dict:
        """
        Queue wait-time statistics per adaptive time bucket.

        wait_seconds = started_at - triggered_at  (only for runs with started_at set)
        Pending runs (no started_at yet) are counted separately.
        """
        granularity = cls.resolve_granularity(since, until)
        trunc_fn = _trunc_fn(granularity, _dialect(db))

        bucket_rows = db.execute(text(f"""
            SELECT
                {trunc_fn('triggered_at')} AS bucket,
                COUNT(*) AS total_runs,
                COUNT(started_at) AS dispatched_runs,
                AVG(CASE WHEN started_at IS NOT NULL
                    THEN {_epoch_diff('started_at', 'triggered_at', _dialect(db))}
                    END) AS avg_wait,
                MAX(CASE WHEN started_at IS NOT NULL
                    THEN {_epoch_diff('started_at', 'triggered_at', _dialect(db))}
                    END) AS max_wait
            FROM test_runs
            WHERE org_id = :org_id
              AND triggered_at >= :since
              AND triggered_at < :until
            GROUP BY bucket
            ORDER BY bucket ASC
        """), {"org_id": str(org_id), "since": since, "until": until}).fetchall()

        points = []
        for row in bucket_rows:
            points.append({
                "date":          _fmt_dt(row[0]),
                "total_runs":    row[1],
                "dispatched":    row[2],
                "avg_wait_seconds": round(row[3], 2) if row[3] is not None else None,
                "max_wait_seconds": round(row[4], 2) if row[4] is not None else None,
            })

        return {
            "since":       since.isoformat(),
            "until":       until.isoformat(),
            "granularity": granularity,
            "data":        points,
        }

    # ── Schedules report ──────────────────────────────────────────────────────

    @classmethod
    def schedules_report(
        cls,
        db: Session,
        org_id: UUID,
        since: datetime,
        until: datetime,
    ) -> dict:
        """
        Per-schedule trigger reliability.

        Uses ScheduledRunHistory.status directly:
          TRIGGERED     → hit (a run was created)
          SKIPPED       → skipped (beat down past miss_threshold)
          TRIGGER_FAILED → failed to create run

        Returns one row per schedule, sorted by miss_rate DESC.
        """
        rows = db.execute(text("""
            SELECT
                j.id AS job_id,
                j.name AS job_name,
                COUNT(*) AS total_fires,
                SUM(CASE WHEN h.status = 'TRIGGERED'     THEN 1 ELSE 0 END) AS triggered,
                SUM(CASE WHEN h.status = 'SKIPPED'       THEN 1 ELSE 0 END) AS skipped,
                SUM(CASE WHEN h.status = 'TRIGGER_FAILED' THEN 1 ELSE 0 END) AS trigger_failed
            FROM scheduled_run_history h
            JOIN scheduled_jobs j ON j.id = h.job_id
            WHERE h.org_id = :org_id
              AND h.triggered_at >= :since
              AND h.triggered_at < :until
            GROUP BY j.id, j.name
            ORDER BY (SUM(CASE WHEN h.status IN ('SKIPPED','TRIGGER_FAILED') THEN 1 ELSE 0 END)
                      * 1.0 / COUNT(*)) DESC
        """), {"org_id": str(org_id), "since": since, "until": until}).fetchall()

        data = []
        for row in rows:
            total = row[2] or 0
            triggered = row[3] or 0
            skipped = row[4] or 0
            failed = row[5] or 0
            missed = skipped + failed
            hit_rate = round(triggered / total, 4) if total else 0.0
            miss_rate = round(missed / total, 4) if total else 0.0
            data.append({
                "job_id":          str(row[0]),
                "job_name":        row[1],
                "total_fires":     total,
                "triggered":       triggered,
                "skipped":         skipped,
                "trigger_failed":  failed,
                "missed":          missed,
                "hit_rate":        hit_rate,
                "miss_rate":       miss_rate,
            })

        return {
            "since":       since.isoformat(),
            "until":       until.isoformat(),
            "granularity": None,
            "data":        data,
        }

    # ── Agents report ─────────────────────────────────────────────────────────

    @classmethod
    def agents_report(
        cls,
        db: Session,
        org_id: UUID,
        since: datetime,
        until: datetime,
    ) -> dict:
        """
        Agent execution statistics for completed runs in the window.

        NOTE: Does NOT compute utilization_percent — insufficient heartbeat history.
        Only completed (terminal) runs are included in duration aggregates.
        """
        rows = db.execute(text("""
            SELECT
                r.agent_id,
                a.name AS agent_name,
                COUNT(*) AS run_count,
                SUM(CASE WHEN r.status = 'COMPLETED' THEN 1 ELSE 0 END) AS passed,
                SUM(CASE WHEN r.status = 'FAILED'    THEN 1 ELSE 0 END) AS failed,
                r.started_at,
                r.completed_at
            FROM test_runs r
            LEFT JOIN agents a ON a.id = r.agent_id
            WHERE r.org_id = :org_id
              AND r.triggered_at >= :since
              AND r.triggered_at < :until
              AND r.agent_id IS NOT NULL
            GROUP BY r.agent_id, a.name, r.started_at, r.completed_at
        """), {"org_id": str(org_id), "since": since, "until": until}).fetchall()

        # Group by agent and collect durations
        from collections import defaultdict
        agents: dict[str, dict] = defaultdict(lambda: {
            "run_count": 0, "passed": 0, "failed": 0,
            "durations": [], "agent_name": None
        })

        for row in rows:
            agent_id = str(row[0])
            agents[agent_id]["agent_name"] = row[1]
            agents[agent_id]["run_count"] += row[2]
            agents[agent_id]["passed"] += row[3]
            agents[agent_id]["failed"] += row[4]
            if row[5] and row[6]:   # started_at and completed_at
                dur = (row[6] - row[5]).total_seconds()
                if dur >= 0:
                    agents[agent_id]["durations"].extend([dur] * row[2])

        data = []
        for agent_id, info in agents.items():
            durs = info["durations"]
            avg_dur = round(sum(durs) / len(durs), 2) if durs else None
            p95_dur = round(cls.percentile_95(durs), 2) if durs else None
            data.append({
                "agent_id":            agent_id,
                "agent_name":          info["agent_name"],
                "run_count":           info["run_count"],
                "passed":              info["passed"],
                "failed":              info["failed"],
                "avg_duration_seconds": avg_dur,
                "p95_duration_seconds": p95_dur,
            })

        # Sort by run_count desc
        data.sort(key=lambda x: x["run_count"], reverse=True)

        return {
            "since":       since.isoformat(),
            "until":       until.isoformat(),
            "granularity": None,
            "data":        data,
        }

    # ── Flakiness report ──────────────────────────────────────────────────────

    @classmethod
    def flakiness_report(
        cls,
        db: Session,
        org_id: UUID,
        since: datetime,
        until: datetime,
        min_score: Optional[float] = None,
    ) -> dict:
        """
        Flaky test leaderboard.

        Only COMPLETED (pass) and FAILED (fail) terminal states are used.
        Transitions between other states are not counted.

        Default filter: eligible_runs >= FLAKINESS_MIN_ELIGIBLE_RUNS AND flip_count >= 1
        Optional: min_score >= 0.0 adds flakiness_score >= min_score
        """
        # Pull ordered terminal results per test case
        rows = db.execute(text("""
            SELECT
                r.test_case_id,
                tc.name AS test_case_name,
                r.status,
                r.triggered_at
            FROM test_runs r
            LEFT JOIN test_cases tc ON tc.id = r.test_case_id
            WHERE r.org_id = :org_id
              AND r.triggered_at >= :since
              AND r.triggered_at < :until
              AND r.status IN ('COMPLETED', 'FAILED')
            ORDER BY r.test_case_id, r.triggered_at ASC, r.id ASC
        """), {"org_id": str(org_id), "since": since, "until": until}).fetchall()

        # Group by test case and compute transitions
        from collections import defaultdict
        test_cases: dict[str, dict] = defaultdict(lambda: {
            "name": None, "statuses": []
        })

        for row in rows:
            tc_id = str(row[0])
            test_cases[tc_id]["name"] = row[1]
            test_cases[tc_id]["statuses"].append(row[2])

        data = []
        min_runs = settings.FLAKINESS_MIN_ELIGIBLE_RUNS

        for tc_id, info in test_cases.items():
            statuses = info["statuses"]
            eligible_runs = len(statuses)
            if eligible_runs < min_runs:
                continue

            passed = statuses.count(_PASS_STATUS)
            failed = statuses.count(_FAIL_STATUS)

            # Count adjacent flips
            flips = sum(
                1 for i in range(1, len(statuses))
                if statuses[i] != statuses[i - 1]
            )

            if flips == 0:
                continue   # stable test — excluded by default

            score = round(flips / (eligible_runs - 1), 4)

            if min_score is not None and score < min_score:
                continue

            data.append({
                "test_case_id":    tc_id,
                "test_case_name":  info["name"],
                "runs":            eligible_runs,
                "passed":          passed,
                "failed":          failed,
                "flip_count":      flips,
                "flakiness_score": score,
            })

        # Sort by flakiness_score descending (worst first)
        data.sort(key=lambda x: x["flakiness_score"], reverse=True)

        return {
            "since":       since.isoformat(),
            "until":       until.isoformat(),
            "granularity": None,
            "data":        data,
        }

    # ── Pass rate report ──────────────────────────────────────────────────────

    @classmethod
    def pass_rate_report(
        cls,
        db: Session,
        org_id: UUID,
        since: datetime,
        until: datetime,
        test_case_id: Optional[UUID] = None,
    ) -> dict:
        """
        Pass% trend per adaptive time bucket.

        Only COMPLETED and FAILED count toward pass rate.
        Optional: filter to a specific test case.
        """
        granularity = cls.resolve_granularity(since, until)
        trunc_fn = _trunc_fn(granularity, _dialect(db))

        params: dict = {"org_id": str(org_id), "since": since, "until": until}
        tc_filter = ""
        if test_case_id:
            tc_filter = "AND test_case_id = :tc_id"
            params["tc_id"] = str(test_case_id)

        rows = db.execute(text(f"""
            SELECT
                {trunc_fn('triggered_at')} AS bucket,
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS passed,
                SUM(CASE WHEN status = 'FAILED'    THEN 1 ELSE 0 END) AS failed
            FROM test_runs
            WHERE org_id = :org_id
              AND triggered_at >= :since
              AND triggered_at < :until
              AND status IN ('COMPLETED', 'FAILED')
              {tc_filter}
            GROUP BY bucket
            ORDER BY bucket ASC
        """), params).fetchall()

        points = []
        for row in rows:
            total = row[1] or 0
            passed = row[2] or 0
            failed = row[3] or 0
            pass_rate = round(passed / total, 4) if total else None
            points.append({
                "date":      _fmt_dt(row[0]),
                "total":     total,
                "passed":    passed,
                "failed":    failed,
                "pass_rate": pass_rate,
            })

        return {
            "since":       since.isoformat(),
            "until":       until.isoformat(),
            "granularity": granularity,
            "data":        points,
        }

    # ── Duration report ───────────────────────────────────────────────────────

    @classmethod
    def duration_report(
        cls,
        db: Session,
        org_id: UUID,
        since: datetime,
        until: datetime,
        test_case_id: Optional[UUID] = None,
    ) -> dict:
        """
        Execution duration trend (avg + p95) per adaptive time bucket.

        Only runs with both started_at and completed_at are included.
        p95 computed in Python (nearest-rank) for cross-DB compatibility.
        Optional: filter to a specific test case.
        """
        granularity = cls.resolve_granularity(since, until)
        trunc_fn = _trunc_fn(granularity, _dialect(db))

        params: dict = {"org_id": str(org_id), "since": since, "until": until}
        tc_filter = ""
        if test_case_id:
            tc_filter = "AND test_case_id = :tc_id"
            params["tc_id"] = str(test_case_id)

        # Fetch raw (bucket, duration_seconds) pairs — compute p95 in Python
        rows = db.execute(text(f"""
            SELECT
                {trunc_fn('triggered_at')} AS bucket,
                {_epoch_diff('completed_at', 'started_at', _dialect(db))} AS duration_s
            FROM test_runs
            WHERE org_id = :org_id
              AND triggered_at >= :since
              AND triggered_at < :until
              AND started_at IS NOT NULL
              AND completed_at IS NOT NULL
              {tc_filter}
            ORDER BY bucket ASC
        """), params).fetchall()

        # Group by bucket and compute stats
        from collections import defaultdict
        buckets: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            bucket_key = _fmt_dt(row[0])
            if row[1] is not None and row[1] >= 0:
                buckets[bucket_key].append(float(row[1]))

        # Emit in sorted bucket order
        points = []
        for bucket_key in sorted(buckets.keys()):
            durs = buckets[bucket_key]
            avg = round(sum(durs) / len(durs), 2) if durs else None
            p95 = round(cls.percentile_95(durs), 2) if durs else None
            points.append({
                "date":                bucket_key,
                "run_count":           len(durs),
                "avg_duration_seconds": avg,
                "p95_duration_seconds": p95,
            })

        return {
            "since":       since.isoformat(),
            "until":       until.isoformat(),
            "granularity": granularity,
            "data":        points,
        }


# ── Private SQL helpers ───────────────────────────────────────────────────────

def _dialect(db: Session) -> str:
    """Use the actual connection dialect, never assume SQLite in production."""
    name = db.get_bind().dialect.name
    return "sqlite" if name == "sqlite" else "postgresql"


def _trunc_fn(granularity: str, dialect: str = "postgresql"):
    if granularity not in {"hour", "day", "week"}:
        raise ValueError("Unsupported report granularity")
    if dialect == "postgresql":
        return lambda col: f"date_trunc('{granularity}', {col})"
    if granularity == "hour":
        return lambda col: f"strftime('%Y-%m-%dT%H:00:00', {col})"
    if granularity == "week":
        # weekday 1 advances to Monday; subtract six days first so Monday stays put.
        return lambda col: f"date({col}, '-6 days', 'weekday 1')"
    return lambda col: f"date({col})"


def _epoch_diff(col_end: str, col_start: str, dialect: str = "postgresql") -> str:
    if dialect == "sqlite":
        return f"((julianday({col_end}) - julianday({col_start})) * 86400.0)"
    return f"EXTRACT(EPOCH FROM ({col_end} - {col_start}))"


def _fmt_dt(value) -> Optional[str]:
    """Format a bucket value as an ISO-8601 string for the response."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
