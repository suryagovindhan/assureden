"""
db/repositories/schedules.py — Phase 4: ScheduledJob CRUD repository.

Wraps ScheduledJob, ScheduledRunHistory, and RetryRecord.

Internal helpers:
  _validate(cron, tz)       — raises ValueError on invalid input
  _compute_next(cron, tz)   — returns next UTC fire time as naive datetime

Public methods:
  create(...)               — validate + compute next_run_at + persist
  get_live(id, org_id)      — excludes soft-deleted
  list(org_id, ...)         — paginated list with optional enabled_only filter
  patch(job, fields)        — partial update; re-validates cron/tz if changed
  enable(job)               — set is_enabled=True; recompute next_run_at
  disable(job)              — set is_enabled=False
  soft_delete(id, org_id, deleted_by)
  list_history(job_id, org_id, limit)
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.db.base import utcnow
from app.models.schedules import ScheduledJob, ScheduledRunHistory
from app.tasks.scheduler import validate_cron, compute_next_run_at


class ScheduleRepository:

    def __init__(self, db: Session):
        self.db = db

    # ── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _validate(cron_expression: str, timezone: str) -> None:
        """Validates cron expression and IANA timezone. Raises ValueError on failure."""
        validate_cron(cron_expression, timezone)

    @staticmethod
    def _compute_next(cron_expression: str, timezone: str,
                      after: Optional[datetime] = None) -> datetime:
        """Returns next UTC fire time as a naive datetime."""
        return compute_next_run_at(cron_expression, timezone, after=after)

    # ── Public API ───────────────────────────────────────────────────────────

    def create(
        self,
        *,
        org_id: uuid.UUID,
        name: str,
        cron_expression: str,
        timezone: str,
        test_case_id: uuid.UUID,
        environment_id: Optional[uuid.UUID] = None,
        priority: str = "NORMAL",
        run_variables: Optional[dict] = None,
        max_retries: int = 0,
        retry_delay_seconds: int = 60,
        backoff_multiplier: float = 1.0,
        max_retry_delay: int = 3600,
        retry_on_timeout: bool = True,
        retry_on_failure: bool = False,
        retry_on_network_error: bool = True,
        max_dispatch_attempts: Optional[int] = None,
        preferred_agent_id: Optional[uuid.UUID] = None,
        preferred_agent_wait_seconds: int = 300,
        miss_threshold_minutes: int = 5,
        description: Optional[str] = None,
        created_by: Optional[uuid.UUID] = None,
    ) -> ScheduledJob:
        self._validate(cron_expression, timezone)
        next_run_at = self._compute_next(cron_expression, timezone)

        job = ScheduledJob(
            org_id=org_id,
            name=name,
            description=description,
            test_case_id=test_case_id,
            environment_id=environment_id,
            cron_expression=cron_expression,
            timezone=timezone,
            next_run_at=next_run_at,
            priority=priority,
            run_variables=run_variables or {},
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds,
            backoff_multiplier=backoff_multiplier,
            max_retry_delay=max_retry_delay,
            retry_on_timeout=retry_on_timeout,
            retry_on_failure=retry_on_failure,
            retry_on_network_error=retry_on_network_error,
            max_dispatch_attempts=max_dispatch_attempts,
            preferred_agent_id=preferred_agent_id,
            preferred_agent_wait_seconds=preferred_agent_wait_seconds,
            miss_threshold_minutes=miss_threshold_minutes,
            is_enabled=True,
            created_by=created_by,
        )
        self.db.add(job)
        return job

    def get_live(self, job_id: uuid.UUID, org_id: uuid.UUID) -> Optional[ScheduledJob]:
        return (
            self.db.query(ScheduledJob)
            .filter(
                ScheduledJob.id == job_id,
                ScheduledJob.org_id == org_id,
                ScheduledJob.deleted_at.is_(None),
            )
            .first()
        )

    def list(
        self,
        org_id: uuid.UUID,
        *,
        enabled_only: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> list[ScheduledJob]:
        q = self.db.query(ScheduledJob).filter(
            ScheduledJob.org_id == org_id,
            ScheduledJob.deleted_at.is_(None),
        )
        if enabled_only:
            q = q.filter(ScheduledJob.is_enabled.is_(True))
        return q.order_by(ScheduledJob.created_at.desc()).offset(offset).limit(limit).all()

    def count(self, org_id: uuid.UUID, enabled_only: bool = False) -> int:
        q = self.db.query(ScheduledJob).filter(
            ScheduledJob.org_id == org_id,
            ScheduledJob.deleted_at.is_(None),
        )
        if enabled_only:
            q = q.filter(ScheduledJob.is_enabled.is_(True))
        return q.count()

    def patch(self, job: ScheduledJob, fields: dict) -> ScheduledJob:
        """
        Apply a partial update. Re-validates cron/tz if either is changed,
        and recomputes next_run_at if cron or tz changed.
        """
        new_cron = fields.get("cron_expression", job.cron_expression)
        new_tz   = fields.get("timezone", job.timezone)

        cron_changed = new_cron != job.cron_expression or new_tz != job.timezone
        if cron_changed:
            self._validate(new_cron, new_tz)

        allowed = {
            "name", "description", "cron_expression", "timezone",
            "environment_id", "priority", "run_variables",
            "max_retries", "retry_delay_seconds", "backoff_multiplier",
            "max_retry_delay", "retry_on_timeout", "retry_on_failure",
            "retry_on_network_error", "max_dispatch_attempts",
            "preferred_agent_id", "preferred_agent_wait_seconds",
            "miss_threshold_minutes",
        }
        for key, value in fields.items():
            if key in allowed:
                setattr(job, key, value)

        if cron_changed:
            job.next_run_at = self._compute_next(job.cron_expression, job.timezone)

        return job

    def enable(self, job: ScheduledJob) -> ScheduledJob:
        job.is_enabled = True
        if job.next_run_at is None:
            job.next_run_at = self._compute_next(job.cron_expression, job.timezone)
        return job

    def disable(self, job: ScheduledJob) -> ScheduledJob:
        job.is_enabled = False
        return job

    def soft_delete(
        self,
        job_id: uuid.UUID,
        org_id: uuid.UUID,
        deleted_by: Optional[uuid.UUID] = None,
    ) -> Optional[ScheduledJob]:
        job = self.get_live(job_id, org_id)
        if job is None:
            return None
        now = utcnow()
        job.deleted_at = now
        job.deleted_by = deleted_by
        job.is_enabled = False
        return job

    def list_history(
        self,
        job_id: uuid.UUID,
        org_id: uuid.UUID,
        limit: int = 50,
    ) -> list[ScheduledRunHistory]:
        return (
            self.db.query(ScheduledRunHistory)
            .filter(
                ScheduledRunHistory.job_id == job_id,
                ScheduledRunHistory.org_id == org_id,
            )
            .order_by(ScheduledRunHistory.triggered_at.desc())
            .limit(limit)
            .all()
        )
