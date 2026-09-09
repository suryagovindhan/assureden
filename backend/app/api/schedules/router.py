"""
api/schedules/router.py — Phase 5 (refactored): thin HTTP boundary.

The router:
  - parses/validates HTTP requests
  - enforces auth + RBAC
  - serialises responses

All business logic lives in ScheduleService.
This router imports NOTHING from ScheduleRepository, scheduler tasks,
_emit_event, or cron helpers directly.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentUser, require_role
from app.db.session import get_db
from app.services.schedule_service import ScheduleService

router = APIRouter(prefix="/schedules", tags=["schedules"])


# ── Request schemas ───────────────────────────────────────────────────────────

class ScheduleCreate(BaseModel):
    name: str
    cron_expression: str
    timezone: str
    test_case_id: UUID
    environment_id: Optional[UUID] = None
    priority: str = "NORMAL"
    run_variables: dict = {}
    max_retries: int = 0
    retry_delay_seconds: int = 60
    backoff_multiplier: float = 1.0
    max_retry_delay: int = 3600
    retry_on_timeout: bool = True
    retry_on_failure: bool = False
    retry_on_network_error: bool = True
    miss_threshold_minutes: int = 10


class SchedulePatch(BaseModel):
    name: Optional[str] = None
    cron_expression: Optional[str] = None
    timezone: Optional[str] = None
    environment_id: Optional[UUID] = None
    priority: Optional[str] = None
    run_variables: Optional[dict] = None
    max_retries: Optional[int] = None
    retry_delay_seconds: Optional[int] = None
    backoff_multiplier: Optional[float] = None
    max_retry_delay: Optional[int] = None
    retry_on_timeout: Optional[bool] = None
    retry_on_failure: Optional[bool] = None
    retry_on_network_error: Optional[bool] = None
    miss_threshold_minutes: Optional[int] = None


# ── Response serialiser ───────────────────────────────────────────────────────

def _job_out(job) -> dict:
    return {
        "id":                    str(job.id),
        "name":                  job.name,
        "cron_expression":       job.cron_expression,
        "timezone":              job.timezone,
        "test_case_id":          str(job.test_case_id),
        "environment_id":        str(job.environment_id) if job.environment_id else None,
        "priority":              job.priority,
        "is_enabled":            job.is_enabled,
        "next_run_at":           job.next_run_at.isoformat() if job.next_run_at else None,
        "last_run_status":       job.last_run_status,
        "max_retries":           job.max_retries,
        "retry_delay_seconds":   job.retry_delay_seconds,
        "backoff_multiplier":    job.backoff_multiplier,
        "max_retry_delay":       job.max_retry_delay,
        "retry_on_timeout":      job.retry_on_timeout,
        "retry_on_failure":      job.retry_on_failure,
        "retry_on_network_error": job.retry_on_network_error,
        "miss_threshold_minutes": job.miss_threshold_minutes,
        "created_at":            job.created_at.isoformat() if job.created_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
def create_schedule(
    body: ScheduleCreate,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    svc = ScheduleService(db)
    try:
        job = svc.create_schedule(
            org_id=current_user.org_id,
            name=body.name,
            cron_expression=body.cron_expression,
            timezone=body.timezone,
            test_case_id=body.test_case_id,
            environment_id=body.environment_id,
            priority=body.priority,
            run_variables=body.run_variables,
            max_retries=body.max_retries,
            retry_delay_seconds=body.retry_delay_seconds,
            backoff_multiplier=body.backoff_multiplier,
            max_retry_delay=body.max_retry_delay,
            retry_on_timeout=body.retry_on_timeout,
            retry_on_failure=body.retry_on_failure,
            retry_on_network_error=body.retry_on_network_error,
            miss_threshold_minutes=body.miss_threshold_minutes,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    db.refresh(job)
    return _job_out(job)


@router.get("")
def list_schedules(
    enabled_only: bool = False,
    offset: int = 0,
    limit: int = 50,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    svc = ScheduleService(db)
    jobs, total = svc.list_schedules(
        org_id=current_user.org_id,
        enabled_only=enabled_only,
        offset=offset,
        limit=limit,
    )
    return {"total": total, "items": [_job_out(j) for j in jobs]}


@router.get("/{job_id}")
def get_schedule(
    job_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    svc = ScheduleService(db)
    job = svc.get_schedule(job_id, current_user.org_id)
    result = _job_out(job)
    result["next_occurrences"] = ScheduleService.preview_occurrences(
        job.cron_expression, job.timezone, count=10
    )
    return result


@router.patch("/{job_id}")
def patch_schedule(
    job_id: UUID,
    body: SchedulePatch,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    svc = ScheduleService(db)
    fields = body.model_dump(exclude_unset=True)
    job = svc.update_schedule(job_id, current_user.org_id, fields)
    db.commit()
    db.refresh(job)
    return _job_out(job)


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role("ADMIN"))],
)
def delete_schedule(
    job_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    svc = ScheduleService(db)
    svc.delete_schedule(job_id, current_user.org_id, deleted_by=current_user.id)
    db.commit()


@router.post("/{job_id}/enable", status_code=status.HTTP_200_OK)
def enable_schedule(
    job_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    svc = ScheduleService(db)
    job = svc.enable_schedule(job_id, current_user.org_id)
    db.commit()
    db.refresh(job)
    return _job_out(job)


@router.post("/{job_id}/disable", status_code=status.HTTP_200_OK)
def disable_schedule(
    job_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    svc = ScheduleService(db)
    job = svc.disable_schedule(job_id, current_user.org_id)
    db.commit()
    db.refresh(job)
    return _job_out(job)


@router.post("/{job_id}/trigger-now", status_code=status.HTTP_201_CREATED)
def trigger_now(
    job_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """
    Fire a scheduled job immediately, bypassing next_run_at.

    **is_enabled is intentionally ignored.**
    trigger-now is an explicit operator action and always fires,
    even if the job is currently disabled. This allows testing or
    re-running a job without re-enabling it.

    Two calls always create two independent QUEUED runs (no deduplication).
    """
    svc = ScheduleService(db)
    run = svc.trigger_now(job_id, current_user.org_id, actor_id=current_user.id)
    db.commit()
    db.refresh(run)
    return {
        "run_id":       str(run.id),
        "status":       run.status,
        "triggered_at": run.triggered_at.isoformat(),
        "test_case_id": str(run.test_case_id),
        "priority":     run.priority,
    }


@router.get("/{job_id}/history")
def get_schedule_history(
    job_id: UUID,
    limit: int = 50,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """Returns schedule metadata + history rows for easy frontend rendering."""
    svc = ScheduleService(db)
    job, history = svc.get_history(job_id, current_user.org_id, limit=limit)
    return {
        "schedule": _job_out(job),
        "count":    len(history),
        "history": [
            {
                "id":           str(h.id),
                "triggered_at": h.triggered_at.isoformat() if h.triggered_at else None,
                "status":       h.status,
                "run_id":       str(h.run_id) if h.run_id else None,
                "trigger_error": h.trigger_error,
            }
            for h in history
        ],
    }
