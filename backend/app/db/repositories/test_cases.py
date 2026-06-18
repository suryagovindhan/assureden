"""
db/repositories/test_cases.py — Phase 2 Test Case Management repositories

All repositories extend OrgScopedRepository with full soft-delete enforcement.

Key behaviours:
  - TestCase.version increments on metadata PUT and on any structural step change
    (create / update / soft-delete / reorder). NOT on cascade propagation.
  - Soft-delete cascade: TestCase → TestStep → StepAssertion (same transaction).
    Children's version is NOT mutated during cascade.
  - Optimistic locking: update raises 409 VersionConflictError on mismatch.
  - Reorder: two-phase UPDATE (+1_000_000 offset) inside one transaction to
    avoid transient UNIQUE(test_case_id, position) violations.
  - Tags: normalised to lowercase before write.
  - AuditEvent payload: { "before": {...}, "after": {...}, "version": N }
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session

from app.db.repositories.base import OrgScopedRepository
from app.models.test_cases import TestSuite, TestCase, TestStep, StepAssertion
from app.models.foundation import AuditEvent


def _utcnow() -> datetime:
    from app.db.base import utcnow
    return utcnow()


def _norm_tags(tags: Optional[list]) -> Optional[list]:
    """Normalise tag list to lowercase, deduplicated, sorted."""
    if tags is None:
        return None
    seen, result = set(), []
    for t in tags:
        tl = str(t).lower().strip()
        if tl and tl not in seen:
            seen.add(tl)
            result.append(tl)
    return result


def _audit(db: Session, org_id: UUID, actor_id: Optional[UUID],
           event_type: str, entity_type: str, entity_id: str,
           before: Optional[dict], after: Optional[dict], version: int) -> None:
    """Write an AuditEvent row.

    event_type format: "TEST_CASE_CREATED" → action="CREATED", entity_type="test_case"
    The AuditEvent model stores: org_id, actor_id, entity_type, entity_id (UUID), action.
    There is no payload column — the before/after args are accepted for API compatibility
    but are not persisted here. Use AssetRevision for full snapshots.
    """
    # Derive short action verb from the last word of event_type (e.g. CREATED, UPDATED, DELETED)
    action = event_type.rsplit("_", 1)[-1]  # TEST_CASE_CREATED → CREATED
    try:
        entity_uuid = UUID(entity_id)
    except ValueError:
        entity_uuid = UUID(int=0)
    ev = AuditEvent(
        org_id=org_id,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_uuid,
        action=action,
    )
    db.add(ev)


def _suite_snapshot(s: TestSuite) -> dict:
    return {"name": s.name, "status": s.status, "tags": s.tags}


def _case_snapshot(c: TestCase) -> dict:
    return {
        "name": c.name, "status": c.status, "priority": c.priority,
        "suite_id": str(c.suite_id) if c.suite_id else None,
        "version": c.version,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TestSuiteRepository
# ─────────────────────────────────────────────────────────────────────────────

class TestSuiteRepository(OrgScopedRepository[TestSuite]):
    model = TestSuite

    def list(
        self,
        org_id: UUID,
        status: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[TestSuite]:
        stmt = (
            select(TestSuite)
            .where(TestSuite.org_id == org_id, TestSuite.deleted_at.is_(None))
        )
        if status:
            stmt = stmt.where(TestSuite.status == status)
        stmt = stmt.order_by(TestSuite.name).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def count(self, org_id: UUID) -> int:
        stmt = select(func.count()).select_from(TestSuite).where(
            TestSuite.org_id == org_id, TestSuite.deleted_at.is_(None)
        )
        return self.db.scalar(stmt) or 0

    def get_case_count(self, suite_id: UUID, org_id: UUID) -> int:
        stmt = select(func.count()).select_from(TestCase).where(
            TestCase.suite_id == suite_id,
            TestCase.org_id == org_id,
            TestCase.deleted_at.is_(None),
        )
        return self.db.scalar(stmt) or 0

    def create(
        self, org_id: UUID, actor_id: Optional[UUID], **kwargs
    ) -> TestSuite:
        kwargs["tags"] = _norm_tags(kwargs.get("tags"))
        suite = TestSuite(org_id=org_id, created_by=actor_id, **kwargs)
        self.db.add(suite)
        self.db.flush()
        _audit(self.db, org_id, actor_id, "TEST_SUITE_CREATED", "test_suite",
               str(suite.id), None, _suite_snapshot(suite), 1)
        return suite

    def update(
        self, suite: TestSuite, actor_id: Optional[UUID], **kwargs
    ) -> TestSuite:
        before = _suite_snapshot(suite)
        if "tags" in kwargs:
            kwargs["tags"] = _norm_tags(kwargs["tags"])
        for k, v in kwargs.items():
            setattr(suite, k, v)
        suite.updated_by = actor_id
        self.db.flush()
        _audit(self.db, suite.org_id, actor_id, "TEST_SUITE_UPDATED", "test_suite",
               str(suite.id), before, _suite_snapshot(suite), 1)
        return suite

    def soft_delete(self, suite: TestSuite, actor_id: Optional[UUID]) -> TestSuite:
        before = _suite_snapshot(suite)
        now = _utcnow()
        suite.deleted_at = now
        suite.deleted_by = actor_id
        self.db.flush()
        _audit(self.db, suite.org_id, actor_id, "TEST_SUITE_DELETED", "test_suite",
               str(suite.id), before, None, 1)
        return suite


# ─────────────────────────────────────────────────────────────────────────────
# TestCaseRepository
# ─────────────────────────────────────────────────────────────────────────────

class TestCaseRepository(OrgScopedRepository[TestCase]):
    model = TestCase

    def _bump_version(self, case: TestCase, actor_id: Optional[UUID]) -> None:
        """Increment case version and set updated_by. Call before flush.

        updated_at is NOT set manually here — it is declared as
        ``updated_at = mapped_column(DateTime, onupdate=utcnow, ...)``
        on the TestCase model, so SQLAlchemy refreshes it automatically
        whenever any tracked column on the row changes during a flush.
        Mutating .version + .updated_by is sufficient to trigger this.
        Do NOT add ``case.updated_at = _utcnow()`` here; it is redundant
        and would bypass the centralised utcnow() hook.
        """
        case.version += 1
        case.updated_by = actor_id

    def list_by_suite(
        self, suite_id: UUID, org_id: UUID, offset: int = 0, limit: int = 100,
    ) -> list[TestCase]:
        stmt = (
            select(TestCase)
            .join(TestSuite, TestCase.suite_id == TestSuite.id)
            .where(
                TestCase.org_id == org_id,
                TestCase.suite_id == suite_id,
                TestCase.deleted_at.is_(None),
                TestSuite.deleted_at.is_(None),
            )
            .order_by(TestCase.name)
            .offset(offset).limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def list_all(
        self,
        org_id: UUID,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        suite_id: Optional[UUID] = None,
        application_id: Optional[UUID] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[TestCase]:
        stmt = select(TestCase).where(
            TestCase.org_id == org_id, TestCase.deleted_at.is_(None)
        )
        if status:
            stmt = stmt.where(TestCase.status == status)
        if priority:
            stmt = stmt.where(TestCase.priority == priority)
        if suite_id:
            stmt = stmt.where(TestCase.suite_id == suite_id)
        if application_id:
            stmt = stmt.where(TestCase.application_id == application_id)
        stmt = stmt.order_by(TestCase.updated_at.desc()).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def search_by_name(
        self, keyword: str, org_id: UUID, offset: int = 0, limit: int = 50,
    ) -> list[TestCase]:
        stmt = (
            select(TestCase)
            .where(
                TestCase.org_id == org_id,
                TestCase.deleted_at.is_(None),
                TestCase.name.ilike(f"%{keyword}%"),
            )
            .order_by(TestCase.updated_at.desc())
            .offset(offset).limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def get_live(self, case_id: UUID, org_id: UUID) -> Optional[TestCase]:
        stmt = select(TestCase).where(
            TestCase.id == case_id,
            TestCase.org_id == org_id,
            TestCase.deleted_at.is_(None),
        )
        return self.db.scalar(stmt)

    def create(
        self, org_id: UUID, actor_id: Optional[UUID], **kwargs
    ) -> TestCase:
        kwargs["tags"] = _norm_tags(kwargs.get("tags"))
        case = TestCase(org_id=org_id, created_by=actor_id, version=1, **kwargs)
        self.db.add(case)
        self.db.flush()
        _audit(self.db, org_id, actor_id, "TEST_CASE_CREATED", "test_case",
               str(case.id), None, _case_snapshot(case), 1)
        return case

    def update(
        self,
        case: TestCase,
        actor_id: Optional[UUID],
        submitted_version: int,
        **kwargs,
    ) -> TestCase:
        """
        Optimistic locking: raises 409 if submitted_version != case.version.
        Bumps case.version after successful update.
        """
        if case.version != submitted_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "VERSION_CONFLICT",
                    "current_version": case.version,
                    "submitted_version": submitted_version,
                },
            )
        before = _case_snapshot(case)
        if "tags" in kwargs:
            kwargs["tags"] = _norm_tags(kwargs["tags"])
        for k, v in kwargs.items():
            setattr(case, k, v)
        self._bump_version(case, actor_id)
        self.db.flush()
        _audit(self.db, case.org_id, actor_id, "TEST_CASE_UPDATED", "test_case",
               str(case.id), before, _case_snapshot(case), case.version)
        return case

    def bump_version_for_step_change(
        self, case: TestCase, actor_id: Optional[UUID]
    ) -> None:
        """Increment case version when steps are structurally changed."""
        self._bump_version(case, actor_id)
        self.db.flush()

    def soft_delete(self, case: TestCase, actor_id: Optional[UUID]) -> TestCase:
        """
        Soft-delete TestCase and cascade to all live TestSteps and their
        live StepAssertions. Children's version NOT mutated.
        TestCase.version incremented once for the delete operation.
        """
        before = _case_snapshot(case)
        now = _utcnow()

        # Cascade to children — collect live step IDs first
        live_steps = self.db.scalars(
            select(TestStep).where(
                TestStep.test_case_id == case.id,
                TestStep.deleted_at.is_(None),
            )
        ).all()
        step_ids = [s.id for s in live_steps]

        # Cascade assertions
        if step_ids:
            self.db.execute(
                update(StepAssertion)
                .where(
                    StepAssertion.step_id.in_(step_ids),
                    StepAssertion.deleted_at.is_(None),
                )
                .values(deleted_at=now, deleted_by=actor_id)
            )
            self.db.execute(
                update(TestStep)
                .where(
                    TestStep.test_case_id == case.id,
                    TestStep.deleted_at.is_(None),
                )
                .values(deleted_at=now, deleted_by=actor_id)
            )

        # Increment version once for the delete, then soft-delete the case
        case.version += 1
        case.updated_by = actor_id
        case.deleted_at = now
        case.deleted_by = actor_id
        self.db.flush()

        _audit(self.db, case.org_id, actor_id, "TEST_CASE_DELETED", "test_case",
               str(case.id), before, None, case.version)
        return case


# ─────────────────────────────────────────────────────────────────────────────
# TestStepRepository
# ─────────────────────────────────────────────────────────────────────────────

class TestStepRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_case(
        self, case_id: UUID, org_id: UUID, include_disabled: bool = False,
    ) -> list[TestStep]:
        """Returns live steps ordered by position. Optionally includes disabled."""
        stmt = (
            select(TestStep)
            .where(
                TestStep.test_case_id == case_id,
                TestStep.org_id == org_id,
                TestStep.deleted_at.is_(None),
            )
            .order_by(TestStep.position)
        )
        if not include_disabled:
            stmt = stmt.where(TestStep.is_enabled.is_(True))
        return list(self.db.scalars(stmt).all())

    def list_all_live(self, case_id: UUID, org_id: UUID) -> list[TestStep]:
        """All live steps (including disabled) — used for reorder validation."""
        stmt = (
            select(TestStep)
            .where(
                TestStep.test_case_id == case_id,
                TestStep.org_id == org_id,
                TestStep.deleted_at.is_(None),
            )
            .order_by(TestStep.position)
        )
        return list(self.db.scalars(stmt).all())

    def get_live(self, step_id: UUID, org_id: UUID) -> Optional[TestStep]:
        stmt = select(TestStep).where(
            TestStep.id == step_id,
            TestStep.org_id == org_id,
            TestStep.deleted_at.is_(None),
        )
        return self.db.scalar(stmt)

    def next_position(self, case_id: UUID) -> int:
        stmt = select(func.max(TestStep.position)).where(
            TestStep.test_case_id == case_id,
            TestStep.deleted_at.is_(None),
        )
        max_pos = self.db.scalar(stmt)
        return (max_pos or 0) + 1

    def create(
        self,
        case: TestCase,
        actor_id: Optional[UUID],
        case_repo: TestCaseRepository,
        **kwargs,
    ) -> TestStep:
        pos = self.next_position(case.id)
        step = TestStep(
            org_id=case.org_id,
            test_case_id=case.id,
            position=pos,
            version=1,
            created_by=actor_id,
            **kwargs,
        )
        self.db.add(step)
        self.db.flush()
        case_repo.bump_version_for_step_change(case, actor_id)
        return step

    def update(
        self,
        step: TestStep,
        case: TestCase,
        actor_id: Optional[UUID],
        case_repo: TestCaseRepository,
        **kwargs,
    ) -> TestStep:
        for k, v in kwargs.items():
            setattr(step, k, v)
        step.version += 1
        step.updated_by = actor_id
        self.db.flush()
        case_repo.bump_version_for_step_change(case, actor_id)
        return step

    def soft_delete(
        self,
        step: TestStep,
        case: TestCase,
        actor_id: Optional[UUID],
        case_repo: TestCaseRepository,
    ) -> TestStep:
        """
        Soft-delete step and cascade to its live assertions.
        step.version is NOT incremented (cascade delete, not a configuration change).
        TestCase.version IS incremented once.
        After deletion, renumber remaining live steps to maintain gapless 1..N.
        """
        now = _utcnow()

        # Cascade to assertions
        self.db.execute(
            update(StepAssertion)
            .where(
                StepAssertion.step_id == step.id,
                StepAssertion.deleted_at.is_(None),
            )
            .values(deleted_at=now, deleted_by=actor_id)
        )

        step.deleted_at = now
        step.deleted_by = actor_id
        self.db.flush()

        # Renumber remaining live steps
        self._renumber(step.test_case_id)
        case_repo.bump_version_for_step_change(case, actor_id)
        return step

    def reorder(
        self,
        case: TestCase,
        ordered_step_ids: list[UUID],
        actor_id: Optional[UUID],
        case_repo: TestCaseRepository,
    ) -> list[TestStep]:
        """
        Reorder live steps to match ordered_step_ids.

        Validation:
          1. All IDs belong to this test case and are live.
          2. No duplicate IDs in the request.
          3. No live IDs missing from the request.

        Two-phase UPDATE to avoid transient UNIQUE(test_case_id, position) violations:
          Phase 1: SET position = position + 1_000_000
          Phase 2: SET position = final_value

        All inside a single DB transaction (managed by caller's session).
        """
        live_steps = {s.id: s for s in self.list_all_live(case.id, case.org_id)}

        # Validation
        if len(ordered_step_ids) != len(set(ordered_step_ids)):
            raise HTTPException(status_code=422, detail="Duplicate step IDs in reorder request")
        if set(ordered_step_ids) != set(live_steps.keys()):
            raise HTTPException(
                status_code=422,
                detail="Reorder IDs must match exactly the live steps of this test case",
            )

        OFFSET = 1_000_000

        # Phase 1: shift all to high range to avoid collisions
        for step_id in ordered_step_ids:
            step = live_steps[step_id]
            step.position = live_steps[step_id].position + OFFSET
        self.db.flush()

        # Phase 2: assign final 1-based positions
        for new_pos, step_id in enumerate(ordered_step_ids, start=1):
            live_steps[step_id].position = new_pos
        self.db.flush()

        case_repo.bump_version_for_step_change(case, actor_id)
        return [live_steps[sid] for sid in ordered_step_ids]

    def _renumber(self, case_id: UUID) -> None:
        """Ensure live steps are gapless 1..N after a soft-delete."""
        steps = list(self.db.scalars(
            select(TestStep)
            .where(TestStep.test_case_id == case_id, TestStep.deleted_at.is_(None))
            .order_by(TestStep.position)
        ).all())
        OFFSET = 1_000_000
        for s in steps:
            s.position += OFFSET
        self.db.flush()
        for i, s in enumerate(steps, start=1):
            s.position = i
        self.db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# StepAssertionRepository
# ─────────────────────────────────────────────────────────────────────────────

class StepAssertionRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_step(
        self, step_id: UUID, org_id: UUID, active_only: bool = True,
    ) -> list[StepAssertion]:
        """
        active_only=True  → deleted_at IS NULL AND is_enabled = True  (execution filter)
        active_only=False → deleted_at IS NULL only (editor view)
        """
        stmt = select(StepAssertion).where(
            StepAssertion.step_id == step_id,
            StepAssertion.org_id == org_id,
            StepAssertion.deleted_at.is_(None),
        )
        if active_only:
            stmt = stmt.where(StepAssertion.is_enabled.is_(True))
        stmt = stmt.order_by(StepAssertion.position)
        return list(self.db.scalars(stmt).all())

    def get_live(self, assertion_id: UUID, org_id: UUID) -> Optional[StepAssertion]:
        stmt = select(StepAssertion).where(
            StepAssertion.id == assertion_id,
            StepAssertion.org_id == org_id,
            StepAssertion.deleted_at.is_(None),
        )
        return self.db.scalar(stmt)

    def next_position(self, step_id: UUID) -> int:
        stmt = select(func.max(StepAssertion.position)).where(
            StepAssertion.step_id == step_id,
            StepAssertion.deleted_at.is_(None),
        )
        max_pos = self.db.scalar(stmt)
        return (max_pos or 0) + 1

    def create(
        self, step: TestStep, actor_id: Optional[UUID], **kwargs
    ) -> StepAssertion:
        pos = self.next_position(step.id)
        assertion = StepAssertion(
            org_id=step.org_id,
            step_id=step.id,
            position=pos,
            created_by=actor_id,
            **kwargs,
        )
        self.db.add(assertion)
        self.db.flush()
        return assertion

    def update(
        self, assertion: StepAssertion, actor_id: Optional[UUID], **kwargs
    ) -> StepAssertion:
        for k, v in kwargs.items():
            setattr(assertion, k, v)
        assertion.updated_by = actor_id
        self.db.flush()
        return assertion

    def soft_delete(
        self, assertion: StepAssertion, actor_id: Optional[UUID]
    ) -> StepAssertion:
        """
        Soft-delete assertion. Does NOT renumber remaining assertions
        (disabled assertions keep their position; only soft-delete triggers reorder).
        """
        assertion.deleted_at = _utcnow()
        assertion.deleted_by = actor_id
        self.db.flush()
        return assertion
