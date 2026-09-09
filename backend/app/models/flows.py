"""
models/flows.py — Phase 3: Reusable Flow and FlowStep ORM models

Flow:
  - Org-scoped, soft-deleted
  - version increments on every step structural change
  - checksum: SHA-256 of canonical step list (sorted keys, no audit fields)
  - created_from_flow_id/version: lineage when duplicated

FlowStep:
  - No FLOW action allowed (no nesting in Phase 3)
  - version increments on every update
  - Two-phase reorder (same pattern as TestStep)

TestStep gains flow_id + flow_version columns (applied via ALTER TABLE migration).
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index,
    Integer, String, Text,
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow
from app.models.test_cases import StepAction  # reuse same enum


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# FlowStep uses the same StepAction enum but FLOW is excluded at the application layer
_step_action_t = SAEnum(StepAction, native_enum=False, validate_strings=True, name="step_action")


class Flow(Base):
    """
    Named, versioned, reusable sequence of steps (atomic — no nesting in Phase 3).

    checksum: SHA-256 of canonical JSON of active steps (position/action/inputs only).
              Computed and updated by FlowRepository on every step write.
    created_from_flow_id/version: lineage for duplicate operations.
    """
    __tablename__ = "flows"
    __table_args__ = (
        Index("idx_flows_org",         "org_id"),
        Index("idx_flows_org_deleted",  "org_id", "deleted_at"),
        Index(
            "uix_flows_org_name_live",
            "org_id", "name",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        CheckConstraint("version >= 1", name="ck_flows_version_positive"),
    )

    id:          Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:      Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), nullable=False)
    name:        Mapped[str]            = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    tags:        Mapped[Optional[str]]  = mapped_column(Text, nullable=True)   # JSON string
    version:     Mapped[int]            = mapped_column(Integer, nullable=False, default=1)
    checksum:    Mapped[str]            = mapped_column(String(64), nullable=False, default="")

    # Lineage (populated by duplicate endpoint)
    created_from_flow_id:    Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_from_version:    Mapped[Optional[int]]       = mapped_column(Integer, nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", use_alter=True, ondelete="RESTRICT", name="fk_flow_created_by"),
        nullable=True,
    )
    created_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    steps: Mapped[list["FlowStep"]] = relationship(
        "FlowStep", back_populates="flow", order_by="FlowStep.position",
    )


class FlowStep(Base):
    """
    One ordered action within a Flow.

    FLOW action is NOT allowed here (no nesting).
    Reorder uses two-phase UPDATE to avoid partial-index violations.
    """
    __tablename__ = "flow_steps"
    __table_args__ = (
        Index("idx_flow_steps_flow",         "flow_id"),
        Index("idx_flow_steps_org",          "org_id"),
        Index("idx_flow_steps_flow_pos",     "flow_id", "position"),
        Index("idx_flow_steps_page_object",  "page_object_id"),
        Index(
            "uix_flow_steps_flow_pos_live",
            "flow_id", "position",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        CheckConstraint("position >= 1", name="ck_flow_steps_position_positive"),
        CheckConstraint("version >= 1",  name="ck_flow_steps_version_positive"),
    )

    id:      Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:  Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    flow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flows.id", ondelete="RESTRICT"), nullable=False,
    )

    position:  Mapped[int] = mapped_column(Integer, nullable=False)
    version:   Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    action:    Mapped[str] = mapped_column(_step_action_t, nullable=False)

    description: Mapped[Optional[str]] = mapped_column(Text,        nullable=True)
    input_value: Mapped[Optional[str]] = mapped_column(Text,        nullable=True)
    target_url:  Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    timeout_ms:  Mapped[int]  = mapped_column(Integer, nullable=False, default=30000)
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_enabled:  Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    page_object_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("page_objects.id", use_alter=True, ondelete="RESTRICT", name="fk_flow_step_po"),
        nullable=True,
    )

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", use_alter=True, ondelete="RESTRICT", name="fk_flow_step_created_by"),
        nullable=True,
    )
    created_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    flow: Mapped["Flow"] = relationship("Flow", back_populates="steps")
