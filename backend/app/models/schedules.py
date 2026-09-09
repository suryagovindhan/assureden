"""
models/schedules.py — Phase 4: ScheduledJob, ScheduledRunHistory, RetryRecord

ScheduledJob:
  - cron_expression: 5-field only; validated via croniter at write time
  - timezone: required IANA string (e.g. "America/New_York"); never assume UTC
  - miss_threshold_minutes: if beat was down and job is past this window → SKIPPED
  - preferred_agent_id: advisory only; release to pool after preferred_agent_wait_seconds
  - max_dispatch_attempts: None = use settings.MAX_DISPATCH_ATTEMPTS global default
  - Retry policy: base_delay + backoff_multiplier + max_retry_delay (flat per-schedule)

ScheduledRunHistory:
  - Snapshots test_case_version/environment_version/priority at fire time
  - Self-contained; no need to join TestRun for basic history
  - run_id is NULL if trigger failed before run creation

RetryRecord:
  - original_run_id ALWAYS points to the root run (never chains retry → retry)
  - attempt: monotonically from original (1, 2, 3...)
  - delay_seconds: actual delay applied (post backoff computation)
  - reason: TIMEOUT | AGENT_LOST | FAILURE | NETWORK_ERROR | MANUAL
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer,
    String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import JSON

from app.db.base import Base, utcnow


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ─────────────────────────────────────────────────────────────────────────────
# ScheduledJob
# ─────────────────────────────────────────────────────────────────────────────

class ScheduledJob(Base):
    """
    A cron-based trigger for recurring test executions.

    timezone is required (no default). Validated against zoneinfo at creation.
    All datetime values are stored as UTC; timezone is only used for
    next_run_at computation via croniter.
    """
    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        Index("idx_scheduled_jobs_org",     "org_id"),
        Index("idx_scheduled_jobs_enabled", "org_id", "next_run_at"),
    )

    id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    name:        Mapped[str]           = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ── Execution Target ─────────────────────────────────────────────────────
    test_case_id:   Mapped[uuid.UUID]        = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_cases.id", ondelete="RESTRICT"), nullable=False)
    environment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", use_alter=True,
                                       ondelete="RESTRICT", name="fk_schedule_env"),
        nullable=True)

    # ── Scheduling ───────────────────────────────────────────────────────────
    cron_expression: Mapped[str]           = mapped_column(String(100), nullable=False)
    timezone:        Mapped[str]           = mapped_column(String(50),  nullable=False)  # required
    next_run_at:     Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_run_at:     Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_run_status: Mapped[Optional[str]]      = mapped_column(String(20), nullable=True)
    # COMPLETED | FAILED | TIMED_OUT | SKIPPED | TRIGGER_FAILED

    # ── Run Config ───────────────────────────────────────────────────────────
    priority:      Mapped[str]           = mapped_column(String(10), nullable=False, default="NORMAL")
    run_variables: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # ── Retry Policy ─────────────────────────────────────────────────────────
    max_retries:              Mapped[int]   = mapped_column(Integer, nullable=False, default=0)
    retry_delay_seconds:      Mapped[int]   = mapped_column(Integer, nullable=False, default=60)
    backoff_multiplier:       Mapped[float] = mapped_column(Float,   nullable=False, default=1.0)
    max_retry_delay:          Mapped[int]   = mapped_column(Integer, nullable=False, default=3600)
    retry_on_timeout:         Mapped[bool]  = mapped_column(Boolean, nullable=False, default=True)
    retry_on_failure:         Mapped[bool]  = mapped_column(Boolean, nullable=False, default=False)
    retry_on_network_error:   Mapped[bool]  = mapped_column(Boolean, nullable=False, default=True)

    # ── Dispatch Limits ───────────────────────────────────────────────────────
    # None → use settings.MAX_DISPATCH_ATTEMPTS (global default)
    max_dispatch_attempts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Preferred Agent (advisory) ────────────────────────────────────────────
    preferred_agent_id:          Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", use_alter=True,
                                       ondelete="SET NULL", name="fk_schedule_agent"),
        nullable=True)
    preferred_agent_wait_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    # After this many seconds, if preferred agent is offline, release to pool

    # ── Operational ───────────────────────────────────────────────────────────
    is_enabled:             Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    miss_threshold_minutes: Mapped[int]  = mapped_column(Integer, nullable=False, default=5)
    # If now > next_run_at + miss_threshold_minutes → SKIPPED (prevents burst after downtime)

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", use_alter=True,
                                       ondelete="RESTRICT", name="fk_schedule_created_by"),
        nullable=True)
    created_at: Mapped[datetime]           = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime]           = mapped_column(DateTime, default=utcnow,
                                                           onupdate=utcnow, nullable=False)

    # ── Soft Delete ──────────────────────────────────────────────────────────
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # ── Relationships ────────────────────────────────────────────────────────
    history: Mapped[list["ScheduledRunHistory"]] = relationship(
        "ScheduledRunHistory", back_populates="job", passive_deletes=True)


# ─────────────────────────────────────────────────────────────────────────────
# ScheduledRunHistory
# ─────────────────────────────────────────────────────────────────────────────

class ScheduledRunHistory(Base):
    """
    One record per fire attempt of a ScheduledJob.

    run_id is NULL if trigger_run() failed before a TestRun was created.
    Snapshots test_case_version/environment_version/priority at fire time so
    history is self-contained without joining TestRun.
    """
    __tablename__ = "scheduled_run_history"
    __table_args__ = (
        Index("idx_schedule_history_job",  "job_id", "triggered_at"),
        Index("idx_schedule_history_org",  "org_id"),
        Index("idx_schedule_history_run",  "run_id"),
    )

    id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_runs.id", use_alter=True,
                                       ondelete="RESTRICT", name="fk_history_run"),
        nullable=True)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # ── Execution inputs snapshotted at fire time ─────────────────────────────
    test_case_version:   Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    environment_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    priority:            Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    triggered_at:  Mapped[datetime]      = mapped_column(DateTime, default=utcnow, nullable=False)
    status:        Mapped[str]           = mapped_column(String(20), nullable=False)
    # TRIGGERED | SKIPPED | TRIGGER_FAILED
    trigger_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ── Relationships ────────────────────────────────────────────────────────
    job: Mapped["ScheduledJob"] = relationship("ScheduledJob", back_populates="history")


# ─────────────────────────────────────────────────────────────────────────────
# RetryRecord
# ─────────────────────────────────────────────────────────────────────────────

class RetryRecord(Base):
    """
    Tracks auto-retry lineage. original_run_id ALWAYS points to the root run —
    never chained (retry1 → retry2 → retry3 would make reporting hard).

    Structure:
        original_run (root)
         ├── RetryRecord(original=root, retry=retry1, attempt=1)
         ├── RetryRecord(original=root, retry=retry2, attempt=2)
         └── RetryRecord(original=root, retry=retry3, attempt=3)

    delay_seconds: actual delay applied after backoff computation.
    reason: why this retry was triggered.
    """
    __tablename__ = "retry_records"
    __table_args__ = (
        Index("idx_retry_records_original", "original_run_id"),
        Index("idx_retry_records_retry",    "retry_run_id"),
        Index("idx_retry_records_org",      "org_id"),
        UniqueConstraint("original_run_id", "attempt", name="uq_retry_original_attempt"),
    )

    id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    original_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="RESTRICT"), nullable=False)
    retry_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="RESTRICT"), nullable=False)

    attempt:        Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3...
    delay_seconds:  Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason:         Mapped[str] = mapped_column(String(50), nullable=False)
    # TIMEOUT | AGENT_LOST | FAILURE | NETWORK_ERROR | MANUAL
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
