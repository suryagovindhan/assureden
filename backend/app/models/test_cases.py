"""
models/test_cases.py — Phase 2 Test Case Management ORM models

All 25 amendments + final critical recommendations incorporated:
  - Soft delete on ALL 4 entities (TestSuite, TestCase, TestStep, StepAssertion)
  - Cascade: TestCase soft-delete propagates to TestStep → StepAssertion (step.version NOT mutated)
  - Stable step.id UUID; position controls order only
  - UNIQUE(test_case_id, position) WHERE deleted_at IS NULL — partial index
  - UNIQUE(step_id, position) WHERE deleted_at IS NULL — partial index on assertions
  - CHECK(position >= 1) on test_steps and step_assertions
  - CHECK(version >= 1) on test_cases and test_steps
  - SQLAlchemy Enum(native_enum=False, validate_strings=True) — string storage
  - ON DELETE RESTRICT on all FKs — physical cascade never happens
  - is_enabled on BOTH TestStep and StepAssertion
  - updated_by on all 4 entities
  - execution_hint engine-agnostic JSON on TestStep
  - Metadata structured as { execution:{}, retry:{}, playwright:{}, browser:{} }
  - version INT DEFAULT 1 on TestCase and TestStep
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, JSON, Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ─────────────────────────────────────────────────────────────────────────────
# Enums  (native_enum=False → stored as VARCHAR; validate_strings=True → DB rejects bad values)
# ─────────────────────────────────────────────────────────────────────────────

class StepAction(str, enum.Enum):
    CLICK          = "CLICK"
    DOUBLE_CLICK   = "DOUBLE_CLICK"
    RIGHT_CLICK    = "RIGHT_CLICK"
    TYPE           = "TYPE"
    APPEND         = "APPEND"
    CLEAR          = "CLEAR"
    SELECT         = "SELECT"
    CHECK          = "CHECK"
    UNCHECK        = "UNCHECK"
    HOVER          = "HOVER"
    SCROLL_TO      = "SCROLL_TO"
    WAIT_FOR       = "WAIT_FOR"
    NAVIGATE       = "NAVIGATE"
    SCREENSHOT     = "SCREENSHOT"
    EXECUTE_SCRIPT = "EXECUTE_SCRIPT"
    DRAG_DROP      = "DRAG_DROP"
    UPLOAD_FILE    = "UPLOAD_FILE"
    PRESS_KEY      = "PRESS_KEY"


class AssertionType(str, enum.Enum):
    VISIBLE          = "VISIBLE"
    NOT_VISIBLE      = "NOT_VISIBLE"
    TEXT_EQUALS      = "TEXT_EQUALS"
    TEXT_CONTAINS    = "TEXT_CONTAINS"
    TEXT_MATCHES     = "TEXT_MATCHES"
    VALUE_EQUALS     = "VALUE_EQUALS"
    ATTRIBUTE_EQUALS = "ATTRIBUTE_EQUALS"
    URL_EQUALS       = "URL_EQUALS"
    URL_CONTAINS     = "URL_CONTAINS"
    TITLE_EQUALS     = "TITLE_EQUALS"
    ELEMENT_COUNT    = "ELEMENT_COUNT"
    ENABLED          = "ENABLED"
    DISABLED         = "DISABLED"
    CHECKED          = "CHECKED"
    UNCHECKED        = "UNCHECKED"


class SuiteStatus(str, enum.Enum):
    ACTIVE   = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class TestStatus(str, enum.Enum):
    DRAFT      = "DRAFT"
    READY      = "READY"
    BLOCKED    = "BLOCKED"
    DEPRECATED = "DEPRECATED"


class TestPriority(str, enum.Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


# SQLAlchemy enum column types (string storage — easy Alembic migrations, SQLite compatible)
_suite_status_t  = SAEnum(SuiteStatus,   native_enum=False, validate_strings=True, name="suite_status")
_test_status_t   = SAEnum(TestStatus,    native_enum=False, validate_strings=True, name="test_status")
_test_priority_t = SAEnum(TestPriority,  native_enum=False, validate_strings=True, name="test_priority")
_step_action_t   = SAEnum(StepAction,    native_enum=False, validate_strings=True, name="step_action")
_assertion_t     = SAEnum(AssertionType, native_enum=False, validate_strings=True, name="assertion_type_enum")


# ─────────────────────────────────────────────────────────────────────────────
# TestSuite
# ─────────────────────────────────────────────────────────────────────────────

class TestSuite(Base):
    """Logical grouping of TestCases. Org-scoped, soft-deleted."""
    __tablename__ = "test_suites"
    __table_args__ = (
        Index("idx_test_suites_org_id",      "org_id"),
        Index("idx_test_suites_org_deleted",  "org_id", "deleted_at"),
        Index("idx_test_suites_org_status",   "org_id", "status"),
        UniqueConstraint("org_id", "name", name="uq_test_suites_org_name"),
    )

    id:          Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:      Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), nullable=False)
    name:        Mapped[str]            = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    status:      Mapped[str]            = mapped_column(_suite_status_t, nullable=False, default=SuiteStatus.ACTIVE)
    tags:        Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", use_alter=True, ondelete="RESTRICT", name="fk_test_suite_owner"),
        nullable=True,
    )
    owner_team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    test_cases: Mapped[list["TestCase"]] = relationship("TestCase", back_populates="suite")


# ─────────────────────────────────────────────────────────────────────────────
# TestCase
# ─────────────────────────────────────────────────────────────────────────────

class TestCase(Base):
    """
    One test scenario — atomic, independently runnable.

    version: starts at 1. Incremented on metadata PUT and on any step
             create/update/soft-delete/reorder. NOT incremented during
             cascade propagation to children.

    Soft-delete cascade: when soft-deleted, all live TestSteps and their
    live StepAssertions are soft-deleted in the same transaction.
    Children's version columns are NOT mutated during cascade.

    Optimistic locking: PUT must supply current version.
    409 response: { error, current_version, submitted_version }
    """
    __tablename__ = "test_cases"
    __table_args__ = (
        Index("idx_test_cases_org_id",       "org_id"),
        Index("idx_test_cases_org_deleted",   "org_id", "deleted_at"),
        Index("idx_test_cases_org_suite",     "org_id", "suite_id"),
        Index("idx_test_cases_org_status",    "org_id", "status"),
        Index("idx_test_cases_org_priority",  "org_id", "priority"),
        Index("idx_test_cases_org_app",       "org_id", "application_id"),
        UniqueConstraint("suite_id", "name", name="uq_test_cases_suite_name"),
        CheckConstraint("version >= 1", name="ck_test_cases_version_positive"),
    )

    id:      Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:  Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    suite_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_suites.id", ondelete="RESTRICT"), nullable=True,
    )
    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", use_alter=True, ondelete="RESTRICT", name="fk_test_case_app"),
        nullable=True,
    )

    name:        Mapped[str]           = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority:    Mapped[str]           = mapped_column(_test_priority_t, nullable=False, default=TestPriority.MEDIUM)
    status:      Mapped[str]           = mapped_column(_test_status_t,   nullable=False, default=TestStatus.DRAFT)
    version:     Mapped[int]           = mapped_column(Integer, nullable=False, default=1)

    tags:                    Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    estimated_duration_secs: Mapped[Optional[int]]  = mapped_column(Integer, nullable=True)
    preconditions:           Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    postconditions:          Mapped[Optional[str]]  = mapped_column(Text, nullable=True)

    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", use_alter=True, ondelete="RESTRICT", name="fk_test_case_owner"),
        nullable=True,
    )
    owner_team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    suite: Mapped[Optional["TestSuite"]] = relationship("TestSuite", back_populates="test_cases")
    steps: Mapped[list["TestStep"]]      = relationship(
        "TestStep", back_populates="test_case", order_by="TestStep.position",
    )


# ─────────────────────────────────────────────────────────────────────────────
# TestStep
# ─────────────────────────────────────────────────────────────────────────────

class TestStep(Base):
    """
    One ordered action within a TestCase.

    id:             immutable UUID — safe for execution log references.
    position:       mutable 1-based integer. Gapless within a live test case.
    version:        incremented on every step update. NOT touched on cascade.

    Partial unique index: UNIQUE(test_case_id, position) WHERE deleted_at IS NULL
    → soft-deleted rows never block reuse of their position.

    Reorder: two-phase UPDATE (+1000000 offset then final values) in one transaction.

    is_enabled: False = step skipped by engine; row retained.
    Execution engine filter: deleted_at IS NULL AND is_enabled = TRUE.

    execution_hint: engine-agnostic self-healing hints.
      { "focus_before_action": true, "iframe_selector": null }
      Framework-specific → metadata.playwright / metadata.browser.

    metadata:
      { "execution": { "clear_before_type": true, "press_enter": false,
                       "retry_count": 2, "retry_interval_ms": 500 },
        "retry": {}, "playwright": {}, "browser": {} }
    """
    __tablename__ = "test_steps"
    __table_args__ = (
        Index("idx_test_steps_org",           "org_id"),
        Index("idx_test_steps_case",          "test_case_id"),
        Index("idx_test_steps_case_position", "test_case_id", "position"),
        Index("idx_test_steps_page_object",   "page_object_id"),
        # Partial unique index — live rows only
        Index(
            "uix_test_steps_case_position_live",
            "test_case_id", "position",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        CheckConstraint("position >= 1", name="ck_test_steps_position_positive"),
        CheckConstraint("version >= 1",  name="ck_test_steps_version_positive"),
    )

    id:           Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:       Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    test_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_cases.id", ondelete="RESTRICT"), nullable=False,
    )

    position: Mapped[int] = mapped_column(Integer, nullable=False)
    action:   Mapped[str] = mapped_column(_step_action_t, nullable=False)
    version:  Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    page_object_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("page_objects.id", use_alter=True, ondelete="RESTRICT", name="fk_test_step_po"),
        nullable=True,
    )

    input_value:  Mapped[Optional[str]] = mapped_column(Text,        nullable=True)
    target_url:   Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    description:  Mapped[Optional[str]] = mapped_column(Text,        nullable=True)

    is_optional:           Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_enabled:            Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timeout_ms:            Mapped[int]  = mapped_column(Integer, nullable=False, default=30000)
    screenshot_on_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    execution_hint: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    step_metadata:  Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    test_case:  Mapped["TestCase"]            = relationship("TestCase", back_populates="steps")
    assertions: Mapped[list["StepAssertion"]] = relationship(
        "StepAssertion", back_populates="step", order_by="StepAssertion.position",
    )


# ─────────────────────────────────────────────────────────────────────────────
# StepAssertion
# ─────────────────────────────────────────────────────────────────────────────

class StepAssertion(Base):
    """
    What must be true AFTER a step executes.

    expected_value: plain text; {{VARIABLE}} placeholders resolved at runtime
                    by Phase 3 variable engine — no schema change needed.
    is_enabled:     False = skipped by engine; retained for debugging history.
                    Disabled assertions are NOT renumbered.
                    Execution filter: deleted_at IS NULL AND is_enabled = TRUE.
    is_negated:     True = assertion must be FALSE to pass.
    is_fatal:       False = warning only; doesn't fail the step.

    Partial unique index: UNIQUE(step_id, position) WHERE deleted_at IS NULL.
    """
    __tablename__ = "step_assertions"
    __table_args__ = (
        Index("idx_step_assertions_step",        "step_id"),
        Index("idx_step_assertions_org",         "org_id"),
        Index("idx_step_assertions_page_object", "target_page_object_id"),
        Index(
            "uix_step_assertions_step_pos_live",
            "step_id", "position",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        CheckConstraint("position >= 1", name="ck_step_assertions_position_positive"),
    )

    id:      Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:  Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_steps.id", ondelete="RESTRICT"), nullable=False,
    )

    position:       Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    assertion_type: Mapped[str] = mapped_column(_assertion_t, nullable=False)

    target_page_object_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("page_objects.id", use_alter=True, ondelete="RESTRICT", name="fk_assertion_po"),
        nullable=True,
    )

    expected_value: Mapped[Optional[str]] = mapped_column(Text,        nullable=True)
    attribute_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    is_negated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_fatal:   Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    step: Mapped["TestStep"] = relationship("TestStep", back_populates="assertions")
