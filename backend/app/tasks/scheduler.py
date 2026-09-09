"""
tasks/scheduler.py — Phase 4: Cron-based scheduled job trigger.

Runs every 60 s via Celery beat.

For each due ScheduledJob:
  - If job is past miss_threshold_minutes → write ScheduledRunHistory(SKIPPED)
  - Otherwise → trigger_run() → write ScheduledRunHistory(TRIGGERED)
  - Compute next_run_at using croniter + zoneinfo (timezone-aware)

Uses FOR UPDATE SKIP LOCKED to handle concurrent beat workers gracefully.

Cron validation (called at job creation, not here):
  - 5-field only (no seconds)
  - Minimum interval >= CRON_MIN_INTERVAL_SECONDS (default 60s)
  - Valid IANA timezone via zoneinfo
"""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Optional

from celery import shared_task
from croniter import croniter
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.base import utcnow
from app.models.schedules import ScheduledJob, ScheduledRunHistory
from app.core.config import settings


def validate_cron(expression: str, timezone: str) -> None:
    """
    Validate a cron expression and timezone before persisting.
    Raises ValueError with a human-readable message on failure.
    """
    # 1. Timezone
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, KeyError):
        raise ValueError(f"Unknown timezone: '{timezone}'. Use an IANA timezone name "
                         f"(e.g. 'America/New_York', 'Europe/London', 'Asia/Kolkata').")

    # 2. 5-field cron only (no seconds support)
    fields = expression.strip().split()
    if len(fields) != 5:
        raise ValueError(
            f"Only 5-field cron expressions are supported (minute hour dom month dow). "
            f"Got {len(fields)} fields: '{expression}'"
        )

    # 3. Valid syntax
    if not croniter.is_valid(expression):
        raise ValueError(f"Invalid cron expression: '{expression}'")

    # 4. Minimum interval check (prevent queue floods)
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    it = croniter(expression, now)
    t1 = it.get_next(datetime)
    t2 = it.get_next(datetime)
    interval = (t2 - t1).total_seconds()
    if interval < settings.CRON_MIN_INTERVAL_SECONDS:
        raise ValueError(
            f"Schedule interval is {interval:.0f}s, which is below the minimum "
            f"allowed interval of {settings.CRON_MIN_INTERVAL_SECONDS}s (1 minute). "
            f"Use a less frequent cron expression."
        )


def compute_next_run_at(expression: str, timezone: str, after: Optional[datetime] = None) -> datetime:
    """
    Compute the next UTC datetime this cron expression will fire.
    `after` defaults to now(). Result is always UTC.
    """
    tz = ZoneInfo(timezone)
    base = (after or utcnow()).astimezone(tz)
    it = croniter(expression, base)
    next_dt = it.get_next(datetime)  # tz-aware in `tz`
    return next_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)  # store as naive UTC


def preview_occurrences(expression: str, timezone: str, count: int = 10) -> list[str]:
    """
    Return the next `count` fire times as ISO 8601 strings with UTC offset.
    Used by GET /schedules/{id} response.
    """
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    it = croniter(expression, now)
    results = []
    for _ in range(count):
        dt = it.get_next(datetime)
        results.append(dt.isoformat())
    return results


def trigger_run_for_schedule(db: Session, job: ScheduledJob) -> Optional[object]:
    """
    Call the execution engine to create a QUEUED TestRun for this ScheduledJob.
    Copies retry policy into run_variables with reserved _retry_* keys.
    Returns the new TestRun or None on failure.

    Public function: called by fire_scheduled_jobs() (Celery beat) AND by
    POST /schedules/{id}/trigger-now (REST API).
    """
    from app.services.execution_engine import trigger_run

    # Merge job-level run_variables with retry policy metadata
    run_vars = dict(job.run_variables or {})
    run_vars["_retry_max_retries"]        = job.max_retries
    run_vars["_retry_delay_seconds"]      = job.retry_delay_seconds
    run_vars["_retry_backoff_multiplier"] = job.backoff_multiplier
    run_vars["_retry_max_retry_delay"]    = job.max_retry_delay
    run_vars["_retry_on_timeout"]         = job.retry_on_timeout
    run_vars["_retry_on_failure"]         = job.retry_on_failure
    run_vars["_retry_on_network_error"]   = job.retry_on_network_error

    # preferred_agent advisory
    preferred_agent_expires_at = None
    from app.db.repositories.test_cases import TestCaseRepository, TestStepRepository
    from app.db.repositories.environments import EnvironmentRepository, EnvironmentVariableRepository

    tc_repo = TestCaseRepository(db)
    tc = tc_repo.get_live(job.test_case_id, job.org_id)
    if tc is None:
        return None

    step_repo = TestStepRepository(db)
    steps = step_repo.list_by_case(tc.id, job.org_id, include_disabled=False)

    environment = None
    env_variables: list = []
    if job.environment_id:
        env_repo = EnvironmentRepository(db)
        environment = env_repo.get_live(job.environment_id, job.org_id)
        if environment:
            var_repo = EnvironmentVariableRepository(db)
            env_variables = var_repo.list_by_env(job.environment_id, job.org_id)

    run, _ = trigger_run(
        db=db,
        test_case=tc,
        steps=steps,
        environment=environment,
        env_variables=env_variables,
        run_variables=run_vars,
        triggered_by=None,   # system trigger
        priority=job.priority,
    )

    # Emit a structured event so the execution timeline shows the scheduler origin.
    from app.services.execution_engine import _emit_event
    from app.models.executions import EventSeverity
    _emit_event(
        db, run.id, "SCHEDULE_TRIGGERED",
        f"Run created by scheduled job '{job.name}' (id={job.id})",
        severity=EventSeverity.INFO,
        metadata={"job_id": str(job.id), "job_name": job.name},
    )
    return run


@shared_task(name="app.tasks.scheduler.fire_scheduled_jobs", bind=True, max_retries=0)
def fire_scheduled_jobs(self) -> dict:
    """
    Called every 60 s by Celery beat.
    Fires all due ScheduledJobs and updates next_run_at.
    """
    db: Session = SessionLocal()
    triggered = 0
    skipped = 0
    failed = 0

    try:
        now = utcnow()

        due_jobs = (
            db.query(ScheduledJob)
            .filter(
                ScheduledJob.is_enabled.is_(True),
                ScheduledJob.deleted_at.is_(None),
                ScheduledJob.next_run_at <= now,
            )
            .with_for_update(skip_locked=True)
            .all()
        )

        for job in due_jobs:
            miss_deadline = job.next_run_at + timedelta(minutes=job.miss_threshold_minutes) \
                if job.next_run_at else None

            if miss_deadline and now > miss_deadline:
                # Missed the window — skip to prevent burst
                history = ScheduledRunHistory(
                    job_id=job.id,
                    org_id=job.org_id,
                    run_id=None,
                    test_case_version=None,
                    environment_version=None,
                    priority=job.priority,
                    status="SKIPPED",
                    trigger_error=f"Missed fire window by "
                                  f"{(now - miss_deadline).total_seconds():.0f}s",
                )
                db.add(history)
                job.last_run_status = "SKIPPED"
                skipped += 1
            else:
                # Fire the job
                run = None
                error_msg = None
                try:
                    run = trigger_run_for_schedule(db, job)
                except Exception as exc:
                    error_msg = str(exc)[:500]
                    failed += 1
                    job.last_run_status = "TRIGGER_FAILED"

                history = ScheduledRunHistory(
                    job_id=job.id,
                    org_id=job.org_id,
                    run_id=run.id if run else None,
                    test_case_version=run.test_case_version if run else None,
                    environment_version=run.environment_version if run else None,
                    priority=job.priority,
                    status="TRIGGERED" if run else "TRIGGER_FAILED",
                    trigger_error=error_msg,
                )
                db.add(history)

                if run:
                    job.last_run_status = "TRIGGERED"
                    triggered += 1

            # Compute next fire time regardless of outcome
            job.last_run_at = now
            try:
                job.next_run_at = compute_next_run_at(job.cron_expression, job.timezone, after=now)
            except Exception:
                job.is_enabled = False  # Disable broken schedules
                job.last_run_status = "TRIGGER_FAILED"

        db.commit()

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {"triggered": triggered, "skipped": skipped, "failed": failed}
