"""
tasks/watchdog.py — Phase 4: Lease recovery + run timeout reaper.

DISPATCHED timeout (agent never started):
  - Requeue until MAX_DISPATCH_ATTEMPTS, then → TIMED_OUT
  - RunEvents: LEASE_EXPIRED → RUN_REQUEUED | RUN_TIMED_OUT

RUNNING timeout (agent lost during execution):
  - Immediately → ABORTED (different semantics from TIMED_OUT)
  - RunEvents: LEASE_EXPIRED → AGENT_LOST

RUNNING execution deadline reached (even with a live agent):
  - TIMED_OUT, RUN_TIMED_OUT event, timeout retry policy.

Both paths call maybe_auto_retry() if configured.
"""

import uuid
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.base import utcnow
from app.models.executions import TestRun, RunStatus, RunEvent, EventSeverity
from app.models.foundation import AgentSession
from app.core.config import settings


def _now() -> datetime:
    return utcnow()


def _max_attempts(run: TestRun) -> int:
    """Effective max dispatch attempts: per-run scheduled job override or global."""
    # If this run has a scheduled_job_id with a custom override, look it up.
    # For now (run has no direct FK to scheduled_job yet), use global default.
    return settings.MAX_DISPATCH_ATTEMPTS


def _next_sequence(db: Session, run_id: uuid.UUID) -> int:
    from app.services.execution_engine import _next_run_event_sequence
    return _next_run_event_sequence(db, run_id)


def _emit(db: Session, run_id: uuid.UUID, event: str, message: str,
          severity: str = EventSeverity.INFO, metadata: dict | None = None) -> None:
    ev = RunEvent(
        run_id=run_id,
        sequence=_next_sequence(db, run_id),
        event=event,
        severity=severity,
        message=message,
        event_metadata=metadata or {},
    )
    db.add(ev)


def _close_agent_session(db: Session, run_id: uuid.UUID, status: str) -> None:
    """Mark any ACTIVE AgentSession for this run as closed."""
    sessions = (
        db.query(AgentSession)
        .filter(AgentSession.execution_id == run_id, AgentSession.status == "ACTIVE")
        .all()
    )
    now = _now()
    for s in sessions:
        s.status = status
        s.ended_at = now


@shared_task(name="app.tasks.watchdog.reap_expired_leases", bind=True, max_retries=0)
def reap_expired_leases(self) -> dict:
    """
    Called every 30 s by Celery beat.

    Scans for runs with expired leases and either requeues or marks terminal.
    Uses FOR UPDATE SKIP LOCKED to avoid conflicts with concurrent workers.
    """
    db: Session = SessionLocal()
    dispatched_requeued = 0
    dispatched_timed_out = 0
    running_aborted = 0
    running_timed_out = 0
    retries_created = 0

    try:
        now = _now()

        # ── DISPATCHED: agent acknowledged but never set status to RUNNING ────
        dispatched_q = (
            db.query(TestRun)
            .filter(
                TestRun.status == RunStatus.DISPATCHED,
                TestRun.lease_expires_at < now,
            )
            .with_for_update(skip_locked=True)
            .all()
        )

        for run in dispatched_q:
            max_att = _max_attempts(run)
            _emit(db, run.id, "LEASE_EXPIRED",
                  f"Lease expired on DISPATCHED run after {run.dispatch_attempt_count} attempt(s)",
                  severity=EventSeverity.WARNING,
                  metadata={"dispatch_attempt_count": run.dispatch_attempt_count,
                             "max_dispatch_attempts": max_att,
                             "agent_id": str(run.agent_id) if run.agent_id else None})

            if run.dispatch_attempt_count < max_att:
                # Requeue — still has attempts remaining
                run.status = RunStatus.QUEUED
                run.lease_id = None
                run.lease_expires_at = None
                run.agent_id = None
                # Poll counts actual dispatches; requeue must not count twice.
                _emit(db, run.id, "RUN_REQUEUED",
                      f"Run requeued (attempt {run.dispatch_attempt_count}/{max_att})",
                      severity=EventSeverity.INFO)
                dispatched_requeued += 1
            else:
                # Exhausted — TIMED_OUT
                run.status = RunStatus.TIMED_OUT
                run.completed_at = now
                run.lease_id = None
                run.lease_expires_at = None
                run.error_message = f"Agent never started after {max_att} dispatch attempts"
                _emit(db, run.id, "RUN_TIMED_OUT",
                      f"Run timed out after {max_att} dispatch attempts",
                      severity=EventSeverity.ERROR)
                _close_agent_session(db, run.id, "TIMED_OUT")
                dispatched_timed_out += 1

                # Auto-retry?
                from app.tasks.auto_retry import maybe_auto_retry
                retry_run = maybe_auto_retry(db, run, reason="TIMEOUT")
                if retry_run:
                    retries_created += 1
                    _emit(db, run.id, "AUTO_RETRY_CREATED",
                          f"Auto-retry run {retry_run.id} created (attempt {retry_run.retry_count})",
                          severity=EventSeverity.INFO,
                          metadata={"retry_run_id": str(retry_run.id)})

        db.commit()

        # ── RUNNING: agent started but went silent ─────────────────────────
        running_q = (
            db.query(TestRun)
            .filter(
                TestRun.status == RunStatus.RUNNING,
                ((TestRun.lease_expires_at <= now) | (TestRun.deadline_at <= now)),
            )
            .with_for_update(skip_locked=True)
            .all()
        )

        for run in running_q:
            if run.deadline_at is not None and run.deadline_at <= now:
                run.status = RunStatus.TIMED_OUT
                run.completed_at = now
                run.lease_id = None
                run.lease_expires_at = None
                run.error_message = "Execution deadline exceeded"
                _emit(db, run.id, "RUN_TIMED_OUT", run.error_message, severity=EventSeverity.ERROR)
                _close_agent_session(db, run.id, "TIMED_OUT")
                running_timed_out += 1
                from app.tasks.auto_retry import maybe_auto_retry
                if maybe_auto_retry(db, run, reason="TIMEOUT"):
                    retries_created += 1
                continue
            _emit(db, run.id, "LEASE_EXPIRED",
                  "Agent lease expired during active execution",
                  severity=EventSeverity.WARNING,
                  metadata={"agent_id": str(run.agent_id) if run.agent_id else None,
                             "passed_steps": run.passed_steps,
                             "total_steps": run.total_steps})

            # RUNNING → ABORTED (not TIMED_OUT — different semantics)
            run.status = RunStatus.ABORTED
            run.completed_at = now
            run.lease_id = None
            run.lease_expires_at = None
            run.error_message = "Agent lost during execution (heartbeat timeout)"
            _emit(db, run.id, "AGENT_LOST",
                  "Agent lost during active execution; run aborted",
                  severity=EventSeverity.ERROR,
                  metadata={"agent_id": str(run.agent_id) if run.agent_id else None})

            _close_agent_session(db, run.id, "CRASHED")
            running_aborted += 1

            # Auto-retry? (retry_on_timeout covers agent loss too)
            from app.tasks.auto_retry import maybe_auto_retry
            retry_run = maybe_auto_retry(db, run, reason="AGENT_LOST")
            if retry_run:
                retries_created += 1
                _emit(db, run.id, "AUTO_RETRY_CREATED",
                      f"Auto-retry run {retry_run.id} created (attempt {retry_run.retry_count})",
                      severity=EventSeverity.INFO,
                      metadata={"retry_run_id": str(retry_run.id)})

        db.commit()

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {
        "dispatched_requeued": dispatched_requeued,
        "dispatched_timed_out": dispatched_timed_out,
        "running_aborted": running_aborted,
        "running_timed_out": running_timed_out,
        "retries_created": retries_created,
    }
