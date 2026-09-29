"""
tasks/auto_retry.py — Phase 4: Auto-retry engine.

Retry lineage is flat — original_run_id ALWAYS points to the root.
Backoff formula: delay = base * (multiplier ^ (attempt - 1)), capped at max_delay.

maybe_auto_retry() is called by:
  - watchdog.reap_expired_leases() for TIMED_OUT / ABORTED
  - Executions router POST /runs/{id}/retry (manual)
"""

import uuid
from datetime import datetime, timedelta
from sqlalchemy import select
from typing import Optional

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.executions import TestRun, RunStatus, RunPriority
from app.models.schedules import RetryRecord


def compute_retry_delay(
    attempt: int,         # 1-based
    base_delay: int,      # retry_delay_seconds
    multiplier: float,    # backoff_multiplier (1.0 = fixed)
    max_delay: int,       # max_retry_delay
) -> int:
    """
    Compute the delay before the next retry attempt.

    Examples:
      base=60, mult=1.0, max=3600 → [60, 60, 60, ...]    (fixed)
      base=60, mult=2.0, max=3600 → [60, 120, 240, ...]  (exponential, capped)
    """
    delay = base_delay * (multiplier ** (attempt - 1))
    return int(min(delay, max_delay))


def _get_retry_policy(run: TestRun) -> dict:
    """
    Return effective retry policy for this run.
    In Phase 4, runs inherit policy from their ScheduledJob if one triggered them,
    or use safe defaults (no auto-retry) for manually triggered runs.
    """
    # Placeholder: look up scheduled job retry policy in Phase 4 scheduler task.
    # For now, fall back to the run's own retry_count vs a stored policy.
    # ScheduledJob → run linkage will be established in the scheduler task;
    # the policy is copied to the run at trigger time via run_variables metadata.
    policy = run.run_variables or {}
    return {
        "max_retries":           int(policy.get("_retry_max_retries", 0)),
        "retry_delay_seconds":   int(policy.get("_retry_delay_seconds", 60)),
        "backoff_multiplier":    float(policy.get("_retry_backoff_multiplier", 1.0)),
        "max_retry_delay":       int(policy.get("_retry_max_retry_delay", 3600)),
        "retry_on_timeout":      bool(policy.get("_retry_on_timeout", True)),
        "retry_on_failure":      bool(policy.get("_retry_on_failure", False)),
        "retry_on_network_error": bool(policy.get("_retry_on_network_error", True)),
    }


def _should_retry(status: str, reason: str, policy: dict) -> bool:
    """Determine whether a retry is warranted given the terminal status and reason."""
    if reason == "MANUAL":
        return True
    if reason in ("TIMEOUT", "AGENT_LOST") and policy["retry_on_timeout"]:
        return True
    if reason == "NETWORK_ERROR" and policy["retry_on_network_error"]:
        return True
    if reason == "FAILURE" and status == RunStatus.FAILED and policy["retry_on_failure"]:
        return True
    return False


def _find_root_run_id(db: Session, run: TestRun) -> uuid.UUID:
    """
    Return the root original_run_id for this run.
    If this run is itself a retry, look up the original via RetryRecord.
    """
    record = (
        db.query(RetryRecord)
        .filter(RetryRecord.retry_run_id == run.id)
        .first()
    )
    return record.original_run_id if record else run.id


def _count_retries(db: Session, original_run_id: uuid.UUID) -> int:
    """Count existing retry attempts for the root run."""
    db.scalar(select(TestRun.id).where(TestRun.id == original_run_id).with_for_update())
    db.flush()
    return (
        db.query(RetryRecord)
        .filter(RetryRecord.original_run_id == original_run_id)
        .count()
    )


def maybe_auto_retry(
    db: Session,
    run: TestRun,
    reason: str,  # TIMEOUT | AGENT_LOST | FAILURE | NETWORK_ERROR
) -> Optional[TestRun]:
    """
    Create a retry run if the retry policy permits it.

    Returns the new TestRun if a retry was created, None otherwise.
    Does NOT commit — caller is responsible for commit.
    """
    policy = _get_retry_policy(run)
    if policy["max_retries"] == 0:
        return None
    if not _should_retry(run.status, reason, policy):
        return None

    original_run_id = _find_root_run_id(db, run)
    existing_attempts = _count_retries(db, original_run_id)
    # Only the latest attempt can create an automatic successor.
    if existing_attempts != (run.retry_count or 0):
        return None
    next_attempt = existing_attempts + 1

    if next_attempt > policy["max_retries"]:
        return None

    delay = compute_retry_delay(
        attempt=next_attempt,
        base_delay=policy["retry_delay_seconds"],
        multiplier=policy["backoff_multiplier"],
        max_delay=policy["max_retry_delay"],
    )

    # Clone the original run
    new_run = TestRun(
        org_id=run.org_id,
        test_case_id=run.test_case_id,
        test_case_version=run.test_case_version,
        environment_id=run.environment_id,
        environment_version=run.environment_version,
        status=RunStatus.QUEUED,
        available_after=utcnow() + timedelta(seconds=delay),
        total_steps=run.total_steps,
        variable_provenance=run.variable_provenance,
        priority=run.priority,
        triggered_by=run.triggered_by,
        run_variables=run.run_variables,
        minimum_protocol_version=run.minimum_protocol_version,
        timeout_seconds=run.timeout_seconds,
        execution_snapshot=run.execution_snapshot,
        execution_snapshot_sha256=run.execution_snapshot_sha256,
        snapshot_schema_version=run.snapshot_schema_version,
        execution_plan_version=run.execution_plan_version,
        retry_count=next_attempt,
    )
    db.add(new_run)
    db.flush()  # get new_run.id without committing

    record = RetryRecord(
        org_id=run.org_id,
        original_run_id=original_run_id,
        retry_run_id=new_run.id,
        attempt=next_attempt,
        delay_seconds=delay,
        reason=reason,
    )
    db.add(record)

    return new_run


def manual_retry(db: Session, run: TestRun, triggered_by: uuid.UUID) -> TestRun:
    """
    Unconditional manual retry (ignores retry policy limits).
    Used by POST /api/runs/{id}/retry endpoint.
    """
    original_run_id = _find_root_run_id(db, run)
    existing_attempts = _count_retries(db, original_run_id)
    next_attempt = existing_attempts + 1

    new_run = TestRun(
        org_id=run.org_id,
        test_case_id=run.test_case_id,
        test_case_version=run.test_case_version,
        environment_id=run.environment_id,
        environment_version=run.environment_version,
        status=RunStatus.QUEUED,
        priority=run.priority,
        triggered_by=triggered_by,
        total_steps=run.total_steps,
        variable_provenance=run.variable_provenance,
        run_variables=run.run_variables,
        minimum_protocol_version=run.minimum_protocol_version,
        timeout_seconds=run.timeout_seconds,
        execution_snapshot=run.execution_snapshot,
        execution_snapshot_sha256=run.execution_snapshot_sha256,
        snapshot_schema_version=run.snapshot_schema_version,
        execution_plan_version=run.execution_plan_version,
        retry_count=next_attempt,
    )
    db.add(new_run)
    db.flush()

    record = RetryRecord(
        org_id=run.org_id,
        original_run_id=original_run_id,
        retry_run_id=new_run.id,
        attempt=next_attempt,
        delay_seconds=0,
        reason="MANUAL",
    )
    db.add(record)

    return new_run
