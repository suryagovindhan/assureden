"""
services/schedule_service.py — Phase 5: Schedule business logic service.

Architecture contract:
  Router  → thin HTTP boundary; calls ScheduleService only
  Service → validation, orchestration, events, transactions
  Repository → SQL only

The router never imports ScheduleRepository, preview_occurrences,
trigger_run_for_schedule, or _emit_event directly. All of that lives here.
"""

from __future__ import annotations

import uuid
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.repositories.schedules import ScheduleRepository
from app.models.schedules import ScheduledJob, ScheduledRunHistory
from app.services.execution_engine import _emit_event
from app.models.executions import EventSeverity


class ScheduleService:
    """
    Centralised schedule business logic.

    All methods that mutate state emit structured RunEvents where a run exists.
    Methods that operate on the schedule itself (not a run) log to
    ScheduledRunHistory or are audit-only.
    """

    def __init__(self, db: Session):
        self.db = db
        self._repo = ScheduleRepository(db)

    # ── Create ────────────────────────────────────────────────────────────────

    def create_schedule(
        self,
        org_id: UUID,
        *,
        name: str,
        cron_expression: str,
        timezone: str,
        test_case_id: UUID,
        environment_id: Optional[UUID] = None,
        priority: str = "NORMAL",
        run_variables: dict | None = None,
        max_retries: int = 0,
        retry_delay_seconds: int = 60,
        backoff_multiplier: float = 1.0,
        max_retry_delay: int = 3600,
        retry_on_timeout: bool = True,
        retry_on_failure: bool = False,
        retry_on_network_error: bool = True,
        miss_threshold_minutes: int = 10,
    ) -> ScheduledJob:
        """
        Validate cron + timezone and create a ScheduledJob.
        Raises ValueError (→ 422) on bad cron or unknown timezone.
        """
        try:
            job = self._repo.create(
                org_id=org_id,
                name=name,
                cron_expression=cron_expression,
                timezone=timezone,
                test_case_id=test_case_id,
                environment_id=environment_id,
                priority=priority,
                run_variables=run_variables or {},
                max_retries=max_retries,
                retry_delay_seconds=retry_delay_seconds,
                backoff_multiplier=backoff_multiplier,
                max_retry_delay=max_retry_delay,
                retry_on_timeout=retry_on_timeout,
                retry_on_failure=retry_on_failure,
                retry_on_network_error=retry_on_network_error,
                miss_threshold_minutes=miss_threshold_minutes,
            )
        except ValueError:
            raise
        self.db.flush()
        return job

    # ── Update (PATCH) ────────────────────────────────────────────────────────

    def update_schedule(
        self,
        job_id: UUID,
        org_id: UUID,
        patch_fields: dict,
    ) -> ScheduledJob:
        """
        Partially update a schedule. Only provided fields are changed.
        Re-validates cron + timezone if either is in patch_fields.
        Raises HTTPException 404 or 422.
        """
        job = self._require_live(job_id, org_id)
        try:
            self._repo.patch(job, patch_fields)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        self.db.flush()
        return job

    # ── Enable / Disable ──────────────────────────────────────────────────────

    def enable_schedule(self, job_id: UUID, org_id: UUID) -> ScheduledJob:
        job = self._require_live(job_id, org_id)
        self._repo.enable(job)
        self.db.flush()
        return job

    def disable_schedule(self, job_id: UUID, org_id: UUID) -> ScheduledJob:
        job = self._require_live(job_id, org_id)
        self._repo.disable(job)
        self.db.flush()
        return job

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete_schedule(
        self, job_id: UUID, org_id: UUID, deleted_by: Optional[UUID] = None
    ) -> None:
        """Soft-delete. Raises 404 if not found."""
        job = self._repo.soft_delete(job_id, org_id, deleted_by=deleted_by)
        if job is None:
            raise HTTPException(status_code=404, detail="Schedule not found")
        self.db.flush()

    # ── Trigger Now ───────────────────────────────────────────────────────────

    def trigger_now(
        self,
        job_id: UUID,
        org_id: UUID,
        actor_id: UUID,
    ) -> object:
        """
        Fire a scheduled job immediately.

        is_enabled is intentionally bypassed — this is an explicit operator action.
        Creates an independent QUEUED run regardless of the job's enable state.
        Two calls always create two independent runs (no deduplication).

        Emits:
          - SCHEDULE_TRIGGERED  (inside trigger_run_for_schedule)
          - RUN_TRIGGERED_MANUALLY  (this method, with actor context)
        """
        from app.tasks.scheduler import trigger_run_for_schedule

        job = self._require_live(job_id, org_id)

        try:
            run = trigger_run_for_schedule(self.db, job)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Trigger failed: {e}")

        if run is None:
            raise HTTPException(
                status_code=422,
                detail="Trigger failed: test case not found or has no runnable steps",
            )

        # Secondary event: identifies this as an explicit operator action.
        # The scheduler path always emits SCHEDULE_TRIGGERED; this supplements it.
        _emit_event(
            self.db, run.id, "RUN_TRIGGERED_MANUALLY",
            f"Run triggered manually via trigger-now by user {actor_id}",
            severity=EventSeverity.INFO,
            metadata={
                "job_id":       str(job.id),
                "job_name":     job.name,
                "triggered_by": str(actor_id),
            },
        )
        self.db.flush()
        return run

    # ── History ───────────────────────────────────────────────────────────────

    def get_history(
        self, job_id: UUID, org_id: UUID, limit: int = 50
    ) -> tuple[ScheduledJob, list[ScheduledRunHistory]]:
        """Returns (job, history_rows) or raises 404."""
        job = self._require_live(job_id, org_id)
        history = self._repo.list_history(job_id, org_id, limit=limit)
        return job, history

    # ── Preview ───────────────────────────────────────────────────────────────

    @staticmethod
    def preview_occurrences(cron: str, tz: str, count: int = 10) -> list[str]:
        """
        Return next N ISO-8601 occurrence strings for a cron expression.
        Delegates to scheduler helper — same source of truth.
        """
        from app.tasks.scheduler import preview_occurrences
        return preview_occurrences(cron, tz, count=count)

    # ── List ─────────────────────────────────────────────────────────────────

    def list_schedules(
        self,
        org_id: UUID,
        enabled_only: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ScheduledJob], int]:
        return self._repo.list_live(org_id, enabled_only=enabled_only, offset=offset, limit=limit)

    def get_schedule(self, job_id: UUID, org_id: UUID) -> ScheduledJob:
        return self._require_live(job_id, org_id)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _require_live(self, job_id: UUID, org_id: UUID) -> ScheduledJob:
        job = self._repo.get_live(job_id, org_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Schedule not found")
        return job
