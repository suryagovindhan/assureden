"""
services/execution_engine.py — Phase 3: Execution orchestration service.

Responsibilities:
  1. Validate run prerequisites (variables, flow versions, snapshot size)
  2. Build execution snapshot
  3. Persist TestRun + RunEvent(QUEUED)
  4. Handle agent poll: transactional lease assignment
  5. Handle agent callbacks: idempotent UPSERT on (run_id, execution_step_id, attempt)
  6. Lease expiry recovery (called by Celery beat task)

# TODO: Priority starvation is an accepted risk for Phase 3.
# A sustained stream of URGENT/HIGH runs can delay LOW runs indefinitely.
# Future phases should implement aging-based scheduling or per-org quotas.

Agent protocol:
  MINIMUM_SUPPORTED_AGENT_PROTOCOL and MAXIMUM_SUPPORTED_AGENT_PROTOCOL are
  enforced during poll. Agents outside the supported range are rejected.
"""

import hashlib
import json
import uuid as _uuid_module
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import utcnow
from app.models.executions import (
    TestRun, StepResult, RunEvent,
    RunStatus, RunPriority, EventSeverity, StepResultStatus,
)
from app.models.foundation import Agent
from app.services.snapshot_builder import (
    build_snapshot, build_agent_payload, compute_snapshot_sha256,
)
from app.services.variable_resolver import ValidationReport


def _now() -> datetime:
    return utcnow()


def _next_run_event_sequence(db: Session, run_id: UUID) -> int:
    """Atomically get the next sequence number for a run's events."""
    stmt = select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id)
    max_seq = db.scalar(stmt)
    return (max_seq or 0) + 1


def _emit_event(
    db: Session,
    run_id: UUID,
    event: str,
    message: str,
    severity: str = EventSeverity.INFO,
    metadata: Optional[dict] = None,
) -> RunEvent:
    """Write a RunEvent with the next sequence number and optional metadata."""
    meta = metadata or {}
    meta_json = json.dumps(meta)
    if len(meta_json.encode("utf-8")) > settings.RUN_EVENT_MAX_METADATA_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"RunEvent metadata exceeds {settings.RUN_EVENT_MAX_METADATA_BYTES} bytes",
        )
    seq = _next_run_event_sequence(db, run_id)
    ev = RunEvent(
        run_id=run_id,
        sequence=seq,
        event=event,
        severity=severity,
        message=message,
        event_metadata=meta,
    )
    db.add(ev)
    return ev


def trigger_run(
    *,
    db: Session,
    test_case,
    steps: list,
    environment=None,
    env_variables: list,
    run_variables: dict,
    triggered_by: UUID,
    priority: str = RunPriority.NORMAL,
    timeout_seconds: Optional[int] = None,
    minimum_protocol_version: int = 1,
    retry_count: int = 0,
) -> tuple[TestRun, ValidationReport]:
    """
    Validate and queue a new TestRun.

    Returns:
        (TestRun, ValidationReport) — run is always returned even if warnings exist.

    Raises:
        HTTPException 422 if there are validation errors or size limit exceeded.
    """
    if timeout_seconds is None:
        timeout_seconds = settings.DEFAULT_EXECUTION_TIMEOUT_SECONDS

    try:
        snapshot, report = build_snapshot(
            test_case=test_case,
            steps=steps,
            environment=environment,
            env_variables=env_variables,
            run_variables=run_variables,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not report.valid:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "VALIDATION_FAILED",
                "valid": False,
                "errors": [
                    {
                        "step": e.step, "field": e.field,
                        "variable": e.variable, "issue": e.issue,
                        "message": e.message,
                    }
                    for e in report.errors
                ],
                "warnings": [
                    {
                        "step": w.step, "field": w.field,
                        "variable": w.variable, "issue": w.issue,
                        "message": w.message,
                    }
                    for w in report.warnings
                ],
            },
        )

    sha256 = snapshot.pop("__sha256", compute_snapshot_sha256(snapshot))

    run = TestRun(
        org_id=test_case.org_id,
        test_case_id=test_case.id,
        test_case_version=test_case.version,
        environment_id=getattr(environment, "id", None),
        environment_version=getattr(environment, "version", None),
        triggered_by=triggered_by,
        status=RunStatus.QUEUED,
        priority=priority,
        run_variables=run_variables,
        variable_provenance=snapshot.get("variable_provenance", {}),
        execution_snapshot=snapshot,
        execution_snapshot_sha256=sha256,
        snapshot_schema_version=snapshot.get("snapshot_schema_version", 1),
        execution_plan_version=snapshot.get("execution_plan_version", 1),
        total_steps=len(snapshot.get("steps", [])),
        timeout_seconds=timeout_seconds,
        minimum_protocol_version=minimum_protocol_version,
        retry_count=retry_count,
    )
    db.add(run)
    db.flush()

    _emit_event(db, run.id, "QUEUED", f"Run queued with priority={priority}")
    return run, report


def poll_for_run(
    *,
    db: Session,
    agent,
    org_id: UUID,
) -> Optional[dict]:
    """
    Atomically claim the highest-priority QUEUED run for this agent.

    Returns the agent payload dict (including plaintext secrets) or None.
    The caller must commit the transaction.
    """
    # Protocol version check
    agent_caps = agent.capabilities or {}
    agent_proto = agent_caps.get("protocol_version", getattr(agent, "protocol_version", 1) or 1)
    if agent_proto < settings.MINIMUM_SUPPORTED_AGENT_PROTOCOL:
        raise HTTPException(
            status_code=400,
            detail=f"Agent protocol version {agent_proto} is below minimum supported ({settings.MINIMUM_SUPPORTED_AGENT_PROTOCOL})",
        )
    if agent_proto > settings.MAXIMUM_SUPPORTED_AGENT_PROTOCOL:
        raise HTTPException(
            status_code=400,
            detail=f"Agent protocol version {agent_proto} exceeds maximum supported ({settings.MAXIMUM_SUPPORTED_AGENT_PROTOCOL})",
        )

    agent_actions = set(agent_caps.get("supported_actions", []))

    # Capability-aware selection: find highest-priority QUEUED run
    # that this agent can handle (required_actions ⊆ supported_actions).
    # Priority ordering is derived from PRIORITY_ORDER (models/executions.py)
    # — the single source of truth for rank values.
    from sqlalchemy import case as sa_case
    from app.models.executions import PRIORITY_ORDER
    priority_case_args = tuple(
        (TestRun.priority == p, rank)
        for p, rank in sorted(PRIORITY_ORDER.items(), key=lambda x: x[1])
    )
    priority_order = sa_case(*priority_case_args, else_=len(PRIORITY_ORDER))
    stmt = (
        select(TestRun)
        .where(
            TestRun.org_id == org_id,
            TestRun.status == RunStatus.QUEUED,
            TestRun.minimum_protocol_version <= agent_proto,
        )
        .order_by(
            priority_order,
            TestRun.triggered_at.asc(),
        )
        .limit(20)  # fetch a small batch to filter by capabilities
        .with_for_update(skip_locked=True)
    )
    candidates = list(db.scalars(stmt).all())

    selected: Optional[TestRun] = None
    for run in candidates:
        # Check required actions
        snapshot = run.execution_snapshot or {}
        required = {s["action"] for s in snapshot.get("steps", []) if s.get("action")}
        if agent_actions and not required.issubset(agent_actions):
            continue   # agent can't handle this run's actions
        selected = run
        break

    if selected is None:
        return None

    # Atomic lease assignment
    lease_id = _uuid_module.uuid4()
    now = _now()
    selected.status = RunStatus.DISPATCHED
    selected.agent_id = agent.id
    selected.agent_version = (agent.capabilities or {}).get("version") or agent.agent_version
    selected.lease_id = lease_id
    selected.lease_expires_at = now + timedelta(seconds=settings.AGENT_LEASE_DURATION_SECONDS)
    selected.dispatch_attempt_count = (selected.dispatch_attempt_count or 0) + 1
    db.flush()

    _emit_event(
        db, selected.id, "AGENT_ASSIGNED",
        f"Dispatched to agent {agent.id} (protocol={agent_proto})",
        metadata={"agent_id": str(agent.id), "lease_id": str(lease_id)},
    )

    # Build transient payload with plaintext secrets
    # Import here to avoid circular deps
    from app.db.repositories.environments import EnvironmentRepository
    env_variables: list = []
    environment = None
    if selected.environment_id:
        env_repo = EnvironmentRepository(db)
        environment = db.get(__import__("app.models.environments", fromlist=["Environment"]).Environment, selected.environment_id)
        from sqlalchemy import select as _select
        from app.models.environments import EnvironmentVariable
        vars_q = _select(EnvironmentVariable).where(
            EnvironmentVariable.environment_id == selected.environment_id,
            EnvironmentVariable.deleted_at.is_(None),
        )
        env_variables = list(db.scalars(vars_q).all())

    payload = build_agent_payload(
        snapshot=selected.execution_snapshot or {},
        env_variables=env_variables,
        run_variables=selected.run_variables or {},
        environment=environment,
        protocol_version=agent_proto,
        run_id=str(selected.id),
        lease_id=str(lease_id),
        timeout_seconds=selected.timeout_seconds,
        test_case_id=str(selected.test_case_id),
        test_case_version=selected.test_case_version,
    )
    return payload


def process_agent_update(
    *,
    db: Session,
    run_id: UUID,
    org_id: UUID,
    lease_id: UUID,
    body: dict,
) -> TestRun:
    """
    Process an idempotent agent callback.
    Verifies lease_id, UPSERTs step results, updates run counters, transitions state.
    """
    run = db.scalar(
        select(TestRun).where(TestRun.id == run_id, TestRun.org_id == org_id)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.lease_id != lease_id:
        raise HTTPException(
            status_code=409,
            detail={"error": "LEASE_MISMATCH", "message": "Stale lease_id — run may have been reclaimed"},
        )

    status_update = body.get("status")
    step_results  = body.get("step_results", [])
    error_message = body.get("error_message")

    # ── Transition to RUNNING on first callback ────────────────
    if run.status == RunStatus.DISPATCHED and step_results:
        run.status = RunStatus.RUNNING
        run.started_at = _now()
        _emit_event(db, run.id, "RUN_STARTED", "Agent started execution")

    # ── Idempotent UPSERT of step results ─────────────────────
    for sr_data in step_results:
        exec_step_id = _uuid_module.UUID(sr_data["execution_step_id"])
        attempt = sr_data.get("attempt", 1)

        existing = db.scalar(
            select(StepResult).where(
                StepResult.run_id == run_id,
                StepResult.execution_step_id == exec_step_id,
                StepResult.attempt == attempt,
            )
        )
        new_status = sr_data.get("status", StepResultStatus.PENDING)
        TERMINAL = {StepResultStatus.PASSED, StepResultStatus.FAILED,
                    StepResultStatus.SKIPPED, StepResultStatus.OPTIONAL_FAILED}

        was_terminal = existing and existing.status in TERMINAL
        now_terminal = new_status in TERMINAL

        if existing is None:
            sr = StepResult(
                org_id=org_id,
                run_id=run_id,
                execution_step_id=exec_step_id,
                step_id=_uuid_module.UUID(sr_data["step_id"]),
                step_version=sr_data.get("step_version", 1),
                position=sr_data["position"],
                attempt=attempt,
                action=sr_data.get("action", ""),
                status=new_status,
                started_at=sr_data.get("started_at"),
                completed_at=sr_data.get("completed_at"),
                duration_ms=sr_data.get("duration_ms"),
                display_value=sr_data.get("display_value"),
                screenshot_url=sr_data.get("screenshot_url"),
                error_message=sr_data.get("error_message"),
                assertions=sr_data.get("assertions", []),
            )
            db.add(sr)
            if now_terminal:
                _increment_counters(run, new_status)
        else:
            # Update if not already terminal (idempotency guard)
            if not was_terminal:
                for field, val in [
                    ("status", new_status),
                    ("completed_at", sr_data.get("completed_at")),
                    ("duration_ms", sr_data.get("duration_ms")),
                    ("display_value", sr_data.get("display_value")),
                    ("screenshot_url", sr_data.get("screenshot_url")),
                    ("error_message", sr_data.get("error_message")),
                    ("assertions", sr_data.get("assertions", [])),
                ]:
                    if val is not None:
                        setattr(existing, field, val)
                if now_terminal:
                    _increment_counters(run, new_status)

    db.flush()

    # ── Final status transition ────────────────────────────────
    if status_update in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.ABORTED):
        run.status = status_update
        run.completed_at = _now()
        if error_message:
            run.error_message = error_message[:500]
        _emit_event(db, run.id, f"RUN_{status_update}", f"Run {status_update.lower()}", severity=(
            EventSeverity.INFO if status_update == RunStatus.COMPLETED else EventSeverity.ERROR
        ))

    return run


def _increment_counters(run: TestRun, step_status: str) -> None:
    if step_status == StepResultStatus.PASSED:
        run.passed_steps = (run.passed_steps or 0) + 1
    elif step_status in (StepResultStatus.FAILED, StepResultStatus.OPTIONAL_FAILED):
        run.failed_steps = (run.failed_steps or 0) + 1
    elif step_status == StepResultStatus.SKIPPED:
        run.skipped_steps = (run.skipped_steps or 0) + 1


def recover_expired_leases(db: Session, org_id: Optional[UUID] = None) -> int:
    """
    Celery beat task: recover DISPATCHED runs with expired leases.

    DISPATCHED + expired lease → QUEUED (clear agent/lease; increment dispatch_attempt_count)
    RUNNING   + expired lease → TIMED_OUT

    Returns number of runs recovered.
    """
    now = _now()
    count = 0

    # ── DISPATCHED → QUEUED ───────────────────────────────────
    stmt = (
        select(TestRun)
        .where(
            TestRun.status == RunStatus.DISPATCHED,
            TestRun.lease_expires_at < now,
        )
    )
    if org_id:
        stmt = stmt.where(TestRun.org_id == org_id)

    for run in db.scalars(stmt).all():
        run.status = RunStatus.QUEUED
        run.agent_id = None
        run.lease_id = None
        run.lease_expires_at = None
        _emit_event(
            db, run.id, "LEASE_EXPIRED",
            "Lease expired while DISPATCHED — returning to QUEUED",
            severity=EventSeverity.WARNING,
        )
        count += 1

    # ── RUNNING → TIMED_OUT ────────────────────────────────────
    stmt2 = (
        select(TestRun)
        .where(
            TestRun.status == RunStatus.RUNNING,
            TestRun.lease_expires_at < now,
        )
    )
    if org_id:
        stmt2 = stmt2.where(TestRun.org_id == org_id)

    for run in db.scalars(stmt2).all():
        run.status = RunStatus.TIMED_OUT
        run.completed_at = now
        _emit_event(
            db, run.id, "HEARTBEAT_TIMEOUT",
            "Agent heartbeat lost while RUNNING — run marked TIMED_OUT",
            severity=EventSeverity.ERROR,
        )
        count += 1

    db.flush()
    return count


# ── ExecutionService ──────────────────────────────────────────────────────────

class ExecutionService:
    """
    Service facade for execution business operations.

    Routers call this class rather than Celery task modules directly.
    This keeps business rules in the service layer and treats Celery tasks
    as orchestration wrappers rather than logic owners.
    """

    @staticmethod
    def manual_retry(
        db: Session,
        run_id: UUID,
        org_id: UUID,
        triggered_by: UUID,
    ) -> "TestRun":
        """
        Unconditional manual retry of a terminal run.

        Wraps auto_retry.manual_retry() and emits a RUN_QUEUED event on the
        original run. Does NOT commit — caller is responsible for commit.

        Raises HTTPException 404 if run not found.
        Raises HTTPException 409 if run is not in a terminal state.
        """
        from app.db.repositories.executions import TestRunRepository
        from app.tasks.auto_retry import manual_retry as _manual_retry

        repo = TestRunRepository(db)
        run = repo.get_run(run_id, org_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")

        terminal_statuses = {RunStatus.FAILED, RunStatus.TIMED_OUT, RunStatus.ABORTED, RunStatus.CANCELLED}
        if run.status not in terminal_statuses:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot retry a run in status '{run.status}'. "
                       f"Only terminal runs (FAILED, TIMED_OUT, ABORTED, CANCELLED) can be retried.",
            )

        retry_run = _manual_retry(db, run, triggered_by=triggered_by)

        _emit_event(
            db, run.id, "MANUAL_RETRY_CREATED",
            f"Manual retry run {retry_run.id} created (attempt {retry_run.retry_count})",
            severity=EventSeverity.INFO,
            metadata={"retry_run_id": str(retry_run.id)},
        )

        return retry_run

