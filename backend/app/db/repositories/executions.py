"""
db/repositories/executions.py — Phase 3: TestRun, StepResult, RunEvent repositories.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.repositories.base import OrgScopedRepository
from app.models.executions import (
    TestRun, StepResult, RunEvent, RunStatus, EventSeverity, PRIORITY_ORDER,
)


def _utcnow() -> datetime:
    return utcnow()


class TestRunRepository(OrgScopedRepository[TestRun]):
    model = TestRun

    def list_all(
        self,
        org_id: UUID,
        test_case_id: Optional[UUID] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[TestRun]:
        stmt = (
            select(TestRun)
            .where(TestRun.org_id == org_id)
        )
        if test_case_id:
            stmt = stmt.where(TestRun.test_case_id == test_case_id)
        if status:
            stmt = stmt.where(TestRun.status == status)
        if priority:
            stmt = stmt.where(TestRun.priority == priority)
        stmt = stmt.order_by(TestRun.triggered_at.desc()).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def count(self, org_id: UUID) -> int:
        return self.db.scalar(
            select(func.count()).select_from(TestRun).where(TestRun.org_id == org_id)
        ) or 0

    def get_run(self, run_id: UUID, org_id: UUID) -> Optional[TestRun]:
        stmt = select(TestRun).where(TestRun.id == run_id, TestRun.org_id == org_id)
        return self.db.scalar(stmt)

    def cancel(self, run: TestRun) -> TestRun:
        """QUEUED → CANCELLED. Returns error if not in QUEUED state."""
        if run.status != RunStatus.QUEUED:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=409,
                detail=f"Cannot cancel a run in status '{run.status}'. Only QUEUED runs can be cancelled.",
            )
        run.status = RunStatus.CANCELLED
        run.completed_at = _utcnow()
        self.db.flush()
        return run

    def abort(self, run: TestRun) -> TestRun:
        """RUNNING → ABORTED. Returns error if not in RUNNING state."""
        if run.status not in (RunStatus.RUNNING, RunStatus.DISPATCHED):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=409,
                detail=f"Cannot abort a run in status '{run.status}'. Only RUNNING or DISPATCHED runs can be aborted.",
            )
        run.status = RunStatus.ABORTED
        run.completed_at = _utcnow()
        self.db.flush()
        return run

    def queue_snapshot(self, org_id: UUID) -> list[dict]:
        """
        Return all QUEUED runs for an org, sorted by priority tier then triggered_at.
        Each item includes:
          - queue_position_overall:  global position in queue (1-based)
          - queue_position_in_tier:  position within the priority tier (1-based)
          - wait_seconds:            elapsed since triggered_at

        Uses PRIORITY_ORDER for consistent ordering across all query sites.
        """
        stmt = (
            select(TestRun)
            .where(TestRun.org_id == org_id, TestRun.status == RunStatus.QUEUED)
            .order_by(
                # Inline CASE using Python post-sort is simpler here since SQLite
                # doesn't support native enums; for PostgreSQL this maps to CASE.
                TestRun.triggered_at  # secondary sort within same priority
            )
        )
        runs = list(self.db.scalars(stmt).all())

        # Sort by PRIORITY_ORDER rank, then triggered_at (FIFO within tier)
        runs.sort(key=lambda r: (PRIORITY_ORDER.get(r.priority, 99), r.triggered_at))

        now = _utcnow()
        tier_counters: dict[str, int] = {}
        result = []

        for overall_pos, run in enumerate(runs, start=1):
            tier = run.priority
            tier_counters[tier] = tier_counters.get(tier, 0) + 1

            wait_seconds = max(0, int((now - run.triggered_at).total_seconds())) \
                if run.triggered_at else 0

            result.append({
                "queue_position_overall":  overall_pos,
                "queue_position_in_tier":  tier_counters[tier],
                "run_id":                  str(run.id),
                "test_case_id":            str(run.test_case_id),
                "priority":                run.priority,
                "triggered_at":            run.triggered_at.isoformat() if run.triggered_at else None,
                "wait_seconds":            wait_seconds,
                "retry_count":             run.retry_count,
                "preferred_agent_id":      str(run.preferred_agent_id) if getattr(run, "preferred_agent_id", None) else None,
            })

        return result


class StepResultRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_run(
        self, run_id: UUID, org_id: UUID
    ) -> list[StepResult]:
        """Return step results ordered by position ASC, attempt ASC."""
        stmt = (
            select(StepResult)
            .where(StepResult.run_id == run_id, StepResult.org_id == org_id)
            .order_by(StepResult.position.asc(), StepResult.attempt.asc())
        )
        return list(self.db.scalars(stmt).all())


class RunEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_run(
        self,
        run_id: UUID,
        severity: Optional[str] = None,
        offset: int = 0,
        limit: int = 200,
    ) -> list[RunEvent]:
        stmt = (
            select(RunEvent)
            .where(RunEvent.run_id == run_id)
        )
        if severity:
            stmt = stmt.where(RunEvent.severity == severity)
        stmt = stmt.order_by(RunEvent.sequence.asc()).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())
