"""
models/executions.py — Phase 3: TestRun, StepResult, RunEvent ORM models

TestRun:
  - Pull-based execution; agents poll for QUEUED runs
  - Transactional lease: lease_id + lease_expires_at set atomically on poll
  - execution_snapshot: immutable JSON (no plaintext secrets); sha256 verified at read
  - snapshot_schema_version: identifies snapshot serialization format
  - priority: LOW | NORMAL | HIGH | URGENT — FIFO within tier
  - CANCELLED: stopped before dispatch; ABORTED: stopped mid-run
  - dispatch_attempt_count: lease recovery counter (separate from user-facing retry_count)
  - environment_version: informational; snapshot.resolved_variables is truth

StepResult:
  - execution_step_id: identifies the specific expanded step instance
    (step_id identifies the authored step; use execution_step_id for result correlation)
  - display_value: sanitized resolved input (secrets replaced with ****)
  - UPSERT key: (run_id, execution_step_id, attempt)
  - attempt: enables per-step retries in future phases

RunEvent:
  - Separate from AuditEvent — machine lifecycle only, never user actions
  - sequence: monotonically increasing per run (avoids timestamp collision)
  - severity: DEBUG | INFO | WARNING | ERROR — filterable
  - metadata: capped at 16 KB at write time (enforced by repository)
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index,
    Integer, String, Text, UniqueConstraint,
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import JSON

from app.db.base import Base, utcnow


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class RunStatus(str, enum.Enum):
    QUEUED     = "QUEUED"
    DISPATCHED = "DISPATCHED"
    RUNNING    = "RUNNING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"
    ABORTED    = "ABORTED"
    CANCELLED  = "CANCELLED"
    TIMED_OUT  = "TIMED_OUT"


class RunPriority(str, enum.Enum):
    LOW    = "LOW"
    NORMAL = "NORMAL"
    HIGH   = "HIGH"
    URGENT = "URGENT"


# Shared ordering map: lower = higher urgency.
# Use this in SQL CASE expressions and Python sorts to avoid scattering
# hard-coded rank values across query sites.
PRIORITY_ORDER: dict[str, int] = {
    RunPriority.URGENT: 0,
    RunPriority.HIGH:   1,
    RunPriority.NORMAL: 2,
    RunPriority.LOW:    3,
}


class StepResultStatus(str, enum.Enum):
    PENDING         = "PENDING"
    RUNNING         = "RUNNING"
    PASSED          = "PASSED"
    FAILED          = "FAILED"
    SKIPPED         = "SKIPPED"
    OPTIONAL_FAILED = "OPTIONAL_FAILED"


class EventSeverity(str, enum.Enum):
    DEBUG   = "DEBUG"
    INFO    = "INFO"
    WARNING = "WARNING"
    ERROR   = "ERROR"


_run_status_t    = SAEnum(RunStatus,        native_enum=False, validate_strings=True, name="run_status")
_run_priority_t  = SAEnum(RunPriority,      native_enum=False, validate_strings=True, name="run_priority")
_step_status_t   = SAEnum(StepResultStatus, native_enum=False, validate_strings=True, name="step_result_status")
_event_severity_t = SAEnum(EventSeverity,   native_enum=False, validate_strings=True, name="event_severity")


class TestRun(Base):
    """One execution of a TestCase against an optional Environment."""
    __tablename__ = "test_runs"
    __table_args__ = (
        Index("idx_test_runs_org_status",    "org_id", "status"),
        Index("idx_test_runs_org_case",      "org_id", "test_case_id"),
        Index("idx_test_runs_org_triggered", "org_id", "triggered_at"),
        Index("idx_test_runs_agent",         "agent_id"),
    )

    id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    test_case_id:      Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), ForeignKey("test_cases.id",  ondelete="RESTRICT"), nullable=False)
    test_case_version: Mapped[int]              = mapped_column(Integer, nullable=False)

    environment_id:      Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("environments.id", use_alter=True, ondelete="RESTRICT", name="fk_run_env"), nullable=True)
    environment_version: Mapped[Optional[int]]       = mapped_column(Integer, nullable=True)  # informational only

    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", use_alter=True, ondelete="RESTRICT", name="fk_run_agent"), nullable=True)
    agent_version: Mapped[Optional[str]]  = mapped_column(String(50), nullable=True)  # captured at dispatch

    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", use_alter=True, ondelete="RESTRICT", name="fk_run_triggered_by"), nullable=True)
    triggered_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, nullable=False)

    status:   Mapped[str] = mapped_column(_run_status_t,    nullable=False, default=RunStatus.QUEUED)
    priority: Mapped[str] = mapped_column(_run_priority_t,  nullable=False, default=RunPriority.NORMAL)

    started_at:   Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ── Leasing ────────────────────────────────────────────────────
    lease_id:             Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    lease_expires_at:     Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    dispatch_attempt_count: Mapped[int]               = mapped_column(Integer, nullable=False, default=0)

    # ── User-facing retry tracking ─────────────────────────────────
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Agent protocol requirements ───────────────────────────────
    minimum_protocol_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ── Run-time overrides ─────────────────────────────────────────
    run_variables:      Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    variable_provenance: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)

    # ── Immutable execution snapshot ──────────────────────────────
    # Contains: steps (with locator_snapshot), flow_versions, resolved_variables (no secrets),
    # secret_variable_keys, variable_provenance
    execution_snapshot:        Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    execution_snapshot_sha256: Mapped[Optional[str]]  = mapped_column(String(64), nullable=True)
    snapshot_schema_version:   Mapped[int]            = mapped_column(Integer, nullable=False, default=1)
    execution_plan_version:    Mapped[int]             = mapped_column(Integer, nullable=False, default=1)

    # ── Counters ───────────────────────────────────────────────────
    total_steps:   Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    passed_steps:  Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    failed_steps:  Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    skipped_steps: Mapped[int]           = mapped_column(Integer, nullable=False, default=0)

    error_message:   Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    timeout_seconds: Mapped[int]           = mapped_column(Integer, nullable=False, default=3600)

    # ── Relationships ─────────────────────────────────────────────
    step_results: Mapped[list["StepResult"]] = relationship("StepResult", back_populates="run")
    events:       Mapped[list["RunEvent"]]   = relationship("RunEvent",   back_populates="run")


class StepResult(Base):
    """
    Result of one expanded step instance within a TestRun.

    execution_step_id: identifies the specific expanded step instance (generated at
    snapshot-build time). Differs from step_id (authored step) — supports future
    parallel branches and selective reruns.

    UPSERT key: (run_id, execution_step_id, attempt) — idempotent agent callbacks.
    display_value: sanitized; secret portions replaced with ****.
    """
    __tablename__ = "step_results"
    __table_args__ = (
        Index("idx_step_results_run",          "run_id"),
        Index("idx_step_results_org_run",      "org_id", "run_id"),
        UniqueConstraint("run_id", "execution_step_id", "attempt", name="uq_step_result_exec_attempt"),
    )

    id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="RESTRICT"), nullable=False)

    execution_step_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)  # expanded instance
    step_id:           Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)  # authored step
    step_version:      Mapped[int]       = mapped_column(Integer, nullable=False)
    position:          Mapped[int]       = mapped_column(Integer, nullable=False)
    attempt:           Mapped[int]       = mapped_column(Integer, nullable=False, default=1)

    action: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(_step_status_t, nullable=False, default=StepResultStatus.PENDING)

    started_at:   Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_ms:  Mapped[Optional[int]]      = mapped_column(Integer, nullable=True)

    display_value:  Mapped[Optional[str]] = mapped_column(Text,        nullable=True)  # secrets = ****
    screenshot_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # URI (file://, s3://, https://)
    error_message:  Mapped[Optional[str]] = mapped_column(Text,        nullable=True)

    assertions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    # [{type, expected, actual, passed, error}]

    run: Mapped["TestRun"] = relationship("TestRun", back_populates="step_results")


class RunEvent(Base):
    """
    Machine-generated lifecycle event for a TestRun.
    Separate from AuditEvent (user-initiated CRUD actions).

    sequence: monotonically increasing per run; unambiguous ordering at same timestamp.
    severity: filterable — DEBUG | INFO | WARNING | ERROR.
    metadata: capped at 16 KB at write time.
    """
    __tablename__ = "run_events"
    __table_args__ = (
        Index("idx_run_events_run",          "run_id"),
        Index("idx_run_events_run_severity", "run_id", "severity"),
        UniqueConstraint("run_id", "sequence", name="uq_run_event_run_seq"),
    )

    id:       Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id:   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="RESTRICT"), nullable=False)
    sequence: Mapped[int]       = mapped_column(Integer, nullable=False)

    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    event:     Mapped[str]      = mapped_column(String(50), nullable=False)
    severity:  Mapped[str]      = mapped_column(_event_severity_t, nullable=False, default=EventSeverity.INFO)
    message:   Mapped[str]      = mapped_column(String(500), nullable=False)
    # 'metadata' is reserved by SQLAlchemy DeclarativeBase — mapped as 'event_metadata' with db column 'event_metadata'
    event_metadata: Mapped[Optional[dict]] = mapped_column("event_metadata", JSON, nullable=True, default=dict)

    run: Mapped["TestRun"] = relationship("TestRun", back_populates="events")
