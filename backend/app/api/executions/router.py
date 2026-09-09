"""
api/executions/router.py — Phase 3/4: Test Run execution API

Includes:
  - POST /runs              — validate + queue
  - GET  /runs/queue        — operator queue snapshot (registered BEFORE /runs/{id})
  - GET  /runs, GET /runs/{id}, GET /runs/{id}/steps, GET /runs/{id}/events
  - GET  /runs/{id}/retry-history  — full retry lineage for a run
  - POST /runs/{id}/cancel, POST /runs/{id}/abort, POST /runs/{id}/retry
  - POST /runs/{id}/agent-update   (requires lease_id header)
  - POST /agents/poll              (requires Agent API key)
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.core.dependencies import CurrentUser
from app.db.session import get_db
from app.db.repositories.executions import TestRunRepository, StepResultRepository, RunEventRepository
from app.db.repositories.environments import EnvironmentRepository, EnvironmentVariableRepository
from app.models.executions import RunStatus, RunPriority
from app.models.environments import EnvironmentVariable
from app.services.execution_engine import (
    trigger_run, poll_for_run, process_agent_update, recover_expired_leases,
    ExecutionService,
)

router = APIRouter(tags=["executions"])


# ── Agent API key helper ───────────────────────────────────────────────────────

def get_agent_from_api_key(
    x_agent_api_key: str = Header(..., alias=settings.AGENT_API_KEY_HEADER),
    db: Session = Depends(get_db),
):
    from app.db.repositories.foundation import AgentRepository
    repo = AgentRepository(db)
    hashed = AgentRepository.hash_api_key(x_agent_api_key)
    agent = repo.get_by_api_key_hash(hashed)
    if agent is None:
        raise HTTPException(status_code=401, detail="Invalid agent API key")
    return agent


# ── Schemas ───────────────────────────────────────────────────────────────────

class TriggerRunRequest(BaseModel):
    test_case_id: UUID
    environment_id: Optional[UUID] = None
    run_variables: dict = {}
    priority: str = RunPriority.NORMAL
    timeout_seconds: Optional[int] = None
    minimum_protocol_version: int = 1


class AgentUpdateRequest(BaseModel):
    lease_id: UUID
    status: Optional[str] = None
    step_results: list[dict] = []
    error_message: Optional[str] = None


def _run_out(run) -> dict:
    return {
        "id":                       str(run.id),
        "org_id":                   str(run.org_id),
        "test_case_id":             str(run.test_case_id),
        "test_case_version":        run.test_case_version,
        "environment_id":           str(run.environment_id) if run.environment_id else None,
        "environment_version":      run.environment_version,
        "agent_id":                 str(run.agent_id) if run.agent_id else None,
        "agent_version":            run.agent_version,
        "triggered_by":             str(run.triggered_by) if run.triggered_by else None,
        "triggered_at":             run.triggered_at.isoformat(),
        "status":                   run.status,
        "priority":                 run.priority,
        "started_at":               run.started_at.isoformat() if run.started_at else None,
        "completed_at":             run.completed_at.isoformat() if run.completed_at else None,
        "retry_count":              run.retry_count,
        "dispatch_attempt_count":   run.dispatch_attempt_count,
        "total_steps":              run.total_steps,
        "passed_steps":             run.passed_steps,
        "failed_steps":             run.failed_steps,
        "skipped_steps":            run.skipped_steps,
        "error_message":            run.error_message,
        "timeout_seconds":          run.timeout_seconds,
        "execution_snapshot_sha256": run.execution_snapshot_sha256,
        "snapshot_schema_version":  run.snapshot_schema_version,
    }


def _step_result_out(sr) -> dict:
    return {
        "id":                str(sr.id),
        "run_id":            str(sr.run_id),
        "execution_step_id": str(sr.execution_step_id),
        "step_id":           str(sr.step_id),
        "step_version":      sr.step_version,
        "position":          sr.position,
        "attempt":           sr.attempt,
        "action":            sr.action,
        "status":            sr.status,
        "started_at":        sr.started_at.isoformat() if sr.started_at else None,
        "completed_at":      sr.completed_at.isoformat() if sr.completed_at else None,
        "duration_ms":       sr.duration_ms,
        "display_value":     sr.display_value,
        "screenshot_url":    sr.screenshot_url,
        "error_message":     sr.error_message,
        "assertions":        sr.assertions or [],
    }


def _event_out(ev) -> dict:
    return {
        "id":        str(ev.id),
        "run_id":    str(ev.run_id),
        "sequence":  ev.sequence,
        "timestamp": ev.timestamp.isoformat(),
        "event":     ev.event,
        "severity":  ev.severity,
        "message":   ev.message,
        "metadata":  ev.event_metadata or {},
    }


# ── Run lifecycle ─────────────────────────────────────────────────────────────

@router.post("/runs", status_code=status.HTTP_201_CREATED)
def trigger(
    body: TriggerRunRequest,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    from app.db.repositories.test_cases import TestCaseRepository, TestStepRepository
    tc_repo = TestCaseRepository(db)
    tc = tc_repo.get_live(body.test_case_id, current_user.org_id)
    if tc is None:
        raise HTTPException(status_code=404, detail="Test case not found")

    step_repo = TestStepRepository(db)
    steps = step_repo.list_by_case(tc.id, current_user.org_id, include_disabled=False)

    environment = None
    env_variables: list = []
    if body.environment_id:
        env_repo = EnvironmentRepository(db)
        environment = env_repo.get_live(body.environment_id, current_user.org_id)
        if environment is None:
            raise HTTPException(status_code=404, detail="Environment not found")
        var_repo = EnvironmentVariableRepository(db)
        env_variables = var_repo.list_by_env(body.environment_id, current_user.org_id)

    run, report = trigger_run(
        db=db,
        test_case=tc,
        steps=steps,
        environment=environment,
        env_variables=env_variables,
        run_variables=body.run_variables,
        triggered_by=current_user.id,
        priority=body.priority,
        timeout_seconds=body.timeout_seconds,
        minimum_protocol_version=body.minimum_protocol_version,
    )
    db.commit()
    db.refresh(run)

    result = _run_out(run)
    result["warnings"] = [
        {"step": w.step, "field": w.field, "issue": w.issue, "message": w.message}
        for w in report.warnings
    ]
    return result


@router.get("/runs/queue")
def get_queue(
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """
    Operator queue snapshot: all QUEUED runs for this org sorted by priority+FIFO.

    NOTE: This route must be registered BEFORE GET /runs/{run_id} to prevent
    FastAPI treating the literal string "queue" as a UUID path parameter.
    """
    repo = TestRunRepository(db)
    return repo.queue_snapshot(current_user.org_id)


@router.get("/runs")
def list_runs(
    test_case_id: Optional[UUID] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    offset: int = 0,
    limit: int = 100,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = TestRunRepository(db)
    runs = repo.list_all(
        current_user.org_id,
        test_case_id=test_case_id,
        status=status,
        priority=priority,
        offset=offset,
        limit=limit,
    )
    total = repo.count(current_user.org_id)
    return {"items": [_run_out(r) for r in runs], "total": total}


@router.get("/runs/{run_id}")
def get_run(
    run_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = TestRunRepository(db)
    run = repo.get_run(run_id, current_user.org_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_out(run)


@router.get("/runs/{run_id}/steps")
def get_run_steps(
    run_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    run_repo = TestRunRepository(db)
    run = run_repo.get_run(run_id, current_user.org_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    sr_repo = StepResultRepository(db)
    results = sr_repo.list_by_run(run_id, current_user.org_id)
    return [_step_result_out(r) for r in results]


@router.get("/runs/{run_id}/events")
def get_run_events(
    run_id: UUID,
    severity: Optional[str] = None,
    offset: int = 0,
    limit: int = 200,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    run_repo = TestRunRepository(db)
    run = run_repo.get_run(run_id, current_user.org_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    ev_repo = RunEventRepository(db)
    events = ev_repo.list_by_run(run_id, severity=severity, offset=offset, limit=limit)
    return [_event_out(e) for e in events]


@router.post("/runs/{run_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_run(
    run_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = TestRunRepository(db)
    run = repo.get_run(run_id, current_user.org_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    repo.cancel(run)
    db.commit()


@router.post("/runs/{run_id}/abort", status_code=status.HTTP_204_NO_CONTENT)
def abort_run(
    run_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = TestRunRepository(db)
    run = repo.get_run(run_id, current_user.org_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    repo.abort(run)
    db.commit()


@router.post("/runs/{run_id}/retry", status_code=status.HTTP_201_CREATED)
def retry_run(
    run_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """
    Unconditional manual retry of a terminal run.
    Creates a new QUEUED run with retry lineage rooted at the original run.
    Only valid for runs in FAILED, TIMED_OUT, ABORTED, or CANCELLED state.
    """
    retry_run_obj = ExecutionService.manual_retry(
        db=db,
        run_id=run_id,
        org_id=current_user.org_id,
        triggered_by=current_user.id,
    )
    db.commit()
    db.refresh(retry_run_obj)
    return _run_out(retry_run_obj)


@router.get("/runs/{run_id}/retry-history")
def get_retry_history(
    run_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """
    Return the full retry lineage for a run.

    The response includes:
    - `original_run_id`: the root of this retry chain (same as run_id if this is the root)
    - `retries`: all retry attempts ordered by attempt number

    Works from any run in the chain — root, first retry, or Nth retry.
    RetryRecord.original_run_id always points to the root, so the lineage
    is always flat and complete regardless of which run you query from.
    """
    from app.models.schedules import RetryRecord  # noqa: PLC0415 (lazy import)

    repo = TestRunRepository(db)
    run = repo.get_run(run_id, current_user.org_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # Determine the root of this retry chain
    root_record = (
        db.query(RetryRecord)
        .filter(RetryRecord.retry_run_id == run_id)
        .first()
    )
    original_run_id = root_record.original_run_id if root_record else run_id

    # Fetch all retries in the chain
    retries = (
        db.query(RetryRecord)
        .filter(RetryRecord.original_run_id == original_run_id)
        .order_by(RetryRecord.attempt.asc())
        .all()
    )

    return {
        "original_run_id": str(original_run_id),
        "retries": [
            {
                "attempt":     r.attempt,
                "run_id":      str(r.retry_run_id),
                "reason":      r.reason,
                "delay_seconds": r.delay_seconds,
            }
            for r in retries
        ],
    }


@router.post("/runs/{run_id}/agent-update")
def agent_update(
    run_id: UUID,
    body: AgentUpdateRequest,
    db: Session = Depends(get_db),
    agent=Depends(get_agent_from_api_key),
):
    run = process_agent_update(
        db=db,
        run_id=run_id,
        org_id=agent.org_id,
        lease_id=body.lease_id,
        body=body.model_dump(),
    )
    db.commit()
    db.refresh(run)
    return _run_out(run)


@router.post("/agents/poll")
def poll(
    db: Session = Depends(get_db),
    agent=Depends(get_agent_from_api_key),
):
    """
    Transactional poll for the highest-priority QUEUED run.
    Returns the agent execute_request payload (with plaintext secrets) or 204.
    """
    payload = poll_for_run(db=db, agent=agent, org_id=agent.org_id)
    if payload is None:
        return {"status": "no_work"}
    db.commit()
    return payload


@router.post("/agents/heartbeat-extended", status_code=status.HTTP_204_NO_CONTENT)
def heartbeat_extended(
    body: dict,
    db: Session = Depends(get_db),
    agent=Depends(get_agent_from_api_key),
):
    """
    Extended heartbeat that updates capabilities including build info, os, architecture.
    The standard /agents/heartbeat remains for backward compatibility.
    """
    from app.db.base import utcnow
    agent.last_heartbeat = utcnow()
    caps = agent.capabilities or {}
    for field in ("version", "build", "os", "architecture", "protocol_version", "supported_actions"):
        if field in body:
            caps[field] = body[field]
    agent.capabilities = caps
    if "running_sessions" in body:
        agent.current_parallel_sessions = body["running_sessions"]
    db.commit()
