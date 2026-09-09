"""
db/repositories/flows.py — Phase 3: Flow and FlowStep repositories.

Key behaviors:
  - Checksum recomputed after every step write
  - Flow.version increments on every step structural change or metadata update
  - Optimistic locking: PUT raises 409 if expected_version != current version
  - FLOW action is FORBIDDEN in FlowStep (no nesting)
  - Reorder uses two-phase UPDATE (same pattern as TestStep)
  - Duplicate: clones Flow + FlowSteps, sets created_from_flow_id/version
"""

import hashlib
import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.repositories.base import OrgScopedRepository
from app.models.flows import Flow, FlowStep
from app.models.foundation import AuditEvent


def _utcnow() -> datetime:
    return utcnow()


def _compute_checksum(db: Session, flow_id: UUID) -> str:
    """
    Compute the canonical SHA-256 checksum for a flow's active steps.

    Canonical form:
      - Include only: position, action, input_value, target_url, timeout_ms,
        is_optional, is_enabled, page_object_id
      - Null values normalised to None (never omitted)
      - Steps sorted by position
      - json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=False)
      - SHA-256 of UTF-8 encoded canonical JSON
    """
    stmt = (
        select(FlowStep)
        .where(FlowStep.flow_id == flow_id, FlowStep.deleted_at.is_(None))
        .order_by(FlowStep.position)
    )
    steps = list(db.scalars(stmt).all())
    canonical_steps = sorted(
        [
            {
                "position":       s.position,
                "action":         s.action,
                "input_value":    s.input_value if s.input_value is not None else None,
                "target_url":     s.target_url if s.target_url is not None else None,
                "timeout_ms":     s.timeout_ms,
                "is_optional":    s.is_optional,
                "is_enabled":     s.is_enabled,
                "page_object_id": str(s.page_object_id) if s.page_object_id else None,
            }
            for s in steps
        ],
        key=lambda x: x["position"],
    )
    canonical = json.dumps(canonical_steps, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _audit(db: Session, org_id: UUID, actor_id: Optional[UUID], action: str, entity_id: UUID) -> None:
    ev = AuditEvent(
        org_id=org_id,
        actor_id=actor_id,
        entity_type="flow",
        entity_id=entity_id,
        action=action,
    )
    db.add(ev)


def _norm_tags(tags: Optional[list]) -> Optional[str]:
    if tags is None:
        return None
    seen, result = set(), []
    for t in tags:
        tl = str(t).lower().strip()
        if tl and tl not in seen:
            seen.add(tl)
            result.append(tl)
    return json.dumps(result)


class FlowRepository(OrgScopedRepository[Flow]):
    model = Flow

    def list_all(
        self,
        org_id: UUID,
        search: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Flow]:
        stmt = (
            select(Flow)
            .where(Flow.org_id == org_id, Flow.deleted_at.is_(None))
        )
        if search:
            stmt = stmt.where(Flow.name.ilike(f"%{search}%"))
        stmt = stmt.order_by(Flow.name).offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def get_live(self, flow_id: UUID, org_id: UUID) -> Optional[Flow]:
        return self.get(flow_id, org_id)

    def count(self, org_id: UUID) -> int:
        stmt = select(func.count()).select_from(Flow).where(
            Flow.org_id == org_id, Flow.deleted_at.is_(None)
        )
        return self.db.scalar(stmt) or 0

    def create(
        self,
        org_id: UUID,
        actor_id: Optional[UUID],
        name: str,
        description: Optional[str] = None,
        tags: Optional[list] = None,
    ) -> Flow:
        flow = Flow(
            org_id=org_id,
            name=name,
            description=description,
            tags=_norm_tags(tags),
            version=1,
            checksum="",   # recomputed after first step is added
            created_by=actor_id,
        )
        self.db.add(flow)
        self.db.flush()
        _audit(self.db, org_id, actor_id, "CREATED", flow.id)
        return flow

    def update(
        self,
        flow: Flow,
        actor_id: Optional[UUID],
        expected_version: int,
        **kwargs,
    ) -> Flow:
        if flow.version != expected_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "VERSION_CONFLICT",
                    "current_version": flow.version,
                    "submitted_version": expected_version,
                },
            )
        if "tags" in kwargs:
            kwargs["tags"] = _norm_tags(kwargs["tags"])
        for k, v in kwargs.items():
            setattr(flow, k, v)
        flow.version += 1
        flow.updated_by = actor_id
        self.db.flush()
        _audit(self.db, flow.org_id, actor_id, "UPDATED", flow.id)
        return flow

    def soft_delete(self, flow: Flow, actor_id: Optional[UUID]) -> Flow:
        now = _utcnow()
        flow.deleted_at = now
        flow.deleted_by = actor_id
        flow.version += 1
        flow.updated_by = actor_id
        self.db.flush()
        _audit(self.db, flow.org_id, actor_id, "DELETED", flow.id)
        return flow

    def duplicate(
        self,
        source_flow: Flow,
        actor_id: Optional[UUID],
        new_name: str,
    ) -> Flow:
        """Clone a flow and all its active steps."""
        new_flow = Flow(
            org_id=source_flow.org_id,
            name=new_name,
            description=source_flow.description,
            tags=source_flow.tags,
            version=1,
            checksum="",
            created_from_flow_id=source_flow.id,
            created_from_version=source_flow.version,
            created_by=actor_id,
        )
        self.db.add(new_flow)
        self.db.flush()

        # Clone live steps
        live_steps = self._get_live_steps(source_flow.id)
        for s in live_steps:
            new_step = FlowStep(
                org_id=new_flow.org_id,
                flow_id=new_flow.id,
                position=s.position,
                version=1,
                action=s.action,
                description=s.description,
                input_value=s.input_value,
                target_url=s.target_url,
                timeout_ms=s.timeout_ms,
                is_optional=s.is_optional,
                is_enabled=s.is_enabled,
                page_object_id=s.page_object_id,
                created_by=actor_id,
            )
            self.db.add(new_step)
        self.db.flush()

        # Recompute checksum for cloned flow
        new_flow.checksum = _compute_checksum(self.db, new_flow.id)
        self.db.flush()
        _audit(self.db, new_flow.org_id, actor_id, "CREATED", new_flow.id)
        return new_flow

    def _get_live_steps(self, flow_id: UUID) -> list[FlowStep]:
        stmt = (
            select(FlowStep)
            .where(FlowStep.flow_id == flow_id, FlowStep.deleted_at.is_(None))
            .order_by(FlowStep.position)
        )
        return list(self.db.scalars(stmt).all())

    def _bump_version(self, flow: Flow, actor_id: Optional[UUID]) -> None:
        """Increment flow version and recompute checksum."""
        flow.version += 1
        flow.updated_by = actor_id
        flow.checksum = _compute_checksum(self.db, flow.id)

    def get_tags(self, flow: Flow) -> list:
        if not flow.tags:
            return []
        try:
            return json.loads(flow.tags)
        except Exception:
            return []


class FlowStepRepository:
    def __init__(self, db: Session):
        self.db = db

    FLOW_ACTION = "FLOW"   # forbidden in FlowStep

    def list_by_flow(self, flow_id: UUID, org_id: UUID) -> list[FlowStep]:
        stmt = (
            select(FlowStep)
            .where(
                FlowStep.flow_id == flow_id,
                FlowStep.org_id == org_id,
                FlowStep.deleted_at.is_(None),
            )
            .order_by(FlowStep.position)
        )
        return list(self.db.scalars(stmt).all())

    def get_live(self, step_id: UUID, org_id: UUID) -> Optional[FlowStep]:
        stmt = select(FlowStep).where(
            FlowStep.id == step_id,
            FlowStep.org_id == org_id,
            FlowStep.deleted_at.is_(None),
        )
        return self.db.scalar(stmt)

    def next_position(self, flow_id: UUID) -> int:
        stmt = select(func.max(FlowStep.position)).where(
            FlowStep.flow_id == flow_id, FlowStep.deleted_at.is_(None)
        )
        max_pos = self.db.scalar(stmt)
        return (max_pos or 0) + 1

    def create(
        self,
        flow: Flow,
        actor_id: Optional[UUID],
        flow_repo: FlowRepository,
        **kwargs,
    ) -> FlowStep:
        if kwargs.get("action") == self.FLOW_ACTION:
            raise HTTPException(
                status_code=422,
                detail="FlowStep action cannot be 'FLOW' — nested flows are not allowed in Phase 3",
            )
        pos = self.next_position(flow.id)
        step = FlowStep(
            org_id=flow.org_id,
            flow_id=flow.id,
            position=pos,
            version=1,
            created_by=actor_id,
            **kwargs,
        )
        self.db.add(step)
        self.db.flush()
        flow_repo._bump_version(flow, actor_id)
        self.db.flush()
        return step

    def update(
        self,
        step: FlowStep,
        flow: Flow,
        actor_id: Optional[UUID],
        flow_repo: FlowRepository,
        **kwargs,
    ) -> FlowStep:
        if kwargs.get("action") == self.FLOW_ACTION:
            raise HTTPException(
                status_code=422,
                detail="FlowStep action cannot be 'FLOW' — nested flows are not allowed in Phase 3",
            )
        for k, v in kwargs.items():
            setattr(step, k, v)
        step.version += 1
        step.updated_by = actor_id
        self.db.flush()
        flow_repo._bump_version(flow, actor_id)
        self.db.flush()
        return step

    def soft_delete(
        self,
        step: FlowStep,
        flow: Flow,
        actor_id: Optional[UUID],
        flow_repo: FlowRepository,
    ) -> FlowStep:
        step.deleted_at = _utcnow()
        step.deleted_by = actor_id
        self.db.flush()
        self._renumber(flow.id)
        flow_repo._bump_version(flow, actor_id)
        self.db.flush()
        return step

    def reorder(
        self,
        flow: Flow,
        ordered_step_ids: list[UUID],
        actor_id: Optional[UUID],
        flow_repo: FlowRepository,
    ) -> list[FlowStep]:
        live_steps = {s.id: s for s in self.list_by_flow(flow.id, flow.org_id)}
        if len(ordered_step_ids) != len(set(ordered_step_ids)):
            raise HTTPException(status_code=422, detail="Duplicate step IDs in reorder request")
        if set(ordered_step_ids) != set(live_steps.keys()):
            raise HTTPException(
                status_code=422,
                detail="Reorder IDs must match exactly the live steps of this flow",
            )
        OFFSET = 1_000_000
        for step_id in ordered_step_ids:
            live_steps[step_id].position += OFFSET
        self.db.flush()
        for new_pos, step_id in enumerate(ordered_step_ids, start=1):
            live_steps[step_id].position = new_pos
        self.db.flush()
        flow_repo._bump_version(flow, actor_id)
        self.db.flush()
        return [live_steps[sid] for sid in ordered_step_ids]

    def _renumber(self, flow_id: UUID) -> None:
        steps = list(self.db.scalars(
            select(FlowStep)
            .where(FlowStep.flow_id == flow_id, FlowStep.deleted_at.is_(None))
            .order_by(FlowStep.position)
        ).all())
        OFFSET = 1_000_000
        for s in steps:
            s.position += OFFSET
        self.db.flush()
        for i, s in enumerate(steps, start=1):
            s.position = i
        self.db.flush()
