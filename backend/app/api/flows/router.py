"""
api/flows/router.py — Phase 3: Reusable Flows API
"""

import json
from typing import Optional, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentUser, require_role
from app.models.test_cases import StepAction
from app.db.session import get_db
from app.db.repositories.flows import FlowRepository, FlowStepRepository

router = APIRouter(prefix="/flows", tags=["flows"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class FlowCreate(BaseModel):
    kind: Literal["FLOW", "BUSINESS_ACTION"] = "FLOW"
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class FlowUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class FlowDuplicate(BaseModel):
    new_name: str = Field(min_length=1, max_length=200)


class FlowStepCreate(BaseModel):
    action: StepAction
    input_value: Optional[str] = None
    target_url: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    timeout_ms: int = Field(30000, ge=100)
    is_optional: bool = False
    is_enabled: bool = True
    page_object_id: Optional[UUID] = None


class FlowStepUpdate(BaseModel):
    action: Optional[StepAction] = None
    input_value: Optional[str] = None
    target_url: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    timeout_ms: Optional[int] = Field(None, ge=100)
    is_optional: Optional[bool] = None
    is_enabled: Optional[bool] = None
    page_object_id: Optional[UUID] = None


class ReorderRequest(BaseModel):
    step_ids: list[UUID]


def _flow_out(flow, flow_repo: FlowRepository) -> dict:
    return {
        "id":                    str(flow.id),
        "org_id":                str(flow.org_id),
        "name":                  flow.name,
        "kind":                  flow.kind,
        "description":           flow.description,
        "tags":                  flow_repo.get_tags(flow),
        "version":               flow.version,
        "checksum":              flow.checksum,
        "created_from_flow_id":  str(flow.created_from_flow_id) if flow.created_from_flow_id else None,
        "created_from_version":  flow.created_from_version,
        "created_at":            flow.created_at.isoformat(),
        "updated_at":            flow.updated_at.isoformat(),
        "created_by":            str(flow.created_by) if flow.created_by else None,
    }


def _step_out(step) -> dict:
    return {
        "id":             str(step.id),
        "flow_id":        str(step.flow_id),
        "position":       step.position,
        "version":        step.version,
        "action":         step.action,
        "input_value":    step.input_value,
        "target_url":     step.target_url,
        "description":    step.description,
        "timeout_ms":     step.timeout_ms,
        "is_optional":    step.is_optional,
        "is_enabled":     step.is_enabled,
        "page_object_id": str(step.page_object_id) if step.page_object_id else None,
        "created_at":     step.created_at.isoformat(),
        "updated_at":     step.updated_at.isoformat(),
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/")
def list_flows(
    search: Optional[str] = None,
    offset: int = 0, limit: int = 100,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = FlowRepository(db)
    flows = repo.list_all(current_user.org_id, search=search, offset=offset, limit=limit)
    total = repo.count(current_user.org_id)
    return {"items": [_flow_out(f, repo) for f in flows], "total": total}


@router.post("/", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_role("TESTER"))])
def create_flow(
    body: FlowCreate,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    from sqlalchemy.exc import IntegrityError
    repo = FlowRepository(db)
    try:
        flow = repo.create(
            org_id=current_user.org_id,
            actor_id=current_user.id,
            name=body.name,
            description=body.description,
            tags=body.tags,
            kind=body.kind,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail=f"Flow name '{body.name}' already exists in this organization",
        )
    db.refresh(flow)
    return _flow_out(flow, repo)


@router.get("/{flow_id}/revisions")
def list_flow_revisions(flow_id: UUID, current_user: CurrentUser = None,
                        db: Session = Depends(get_db)):
    from sqlalchemy import select
    from app.models.foundation import AssetRevision
    flow = FlowRepository(db).get_live(flow_id, current_user.org_id)
    if flow is None:
        raise HTTPException(404, "Flow not found")
    rows = db.scalars(select(AssetRevision).where(
        AssetRevision.asset_type == "Flow", AssetRevision.asset_id == flow_id,
        AssetRevision.org_id == current_user.org_id).order_by(AssetRevision.revision.desc())).all()
    versions = [{"version": r.revision, "checksum": r.snapshot["checksum"],
                 "name": r.snapshot["name"], "step_count": len(r.snapshot["steps"])} for r in rows]
    if not any(r["version"] == flow.version for r in versions):
        from app.services.flow_revisions import authored_snapshot
        versions.insert(0, {"version": flow.version, "checksum": flow.checksum,
                            "name": flow.name, "step_count": len(authored_snapshot(db, flow)["steps"])})
    return versions


@router.get("/{flow_id}/revisions/{version}")
def get_flow_revision(flow_id: UUID, version: int, current_user: CurrentUser = None,
                      db: Session = Depends(get_db)):
    from app.services.flow_revisions import get_revision
    flow = FlowRepository(db).get_live(flow_id, current_user.org_id)
    if flow is None:
        raise HTTPException(404, "Flow not found")
    try:
        return {"version": version, **get_revision(db, flow, version)}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{flow_id}")
def get_flow(
    flow_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = FlowRepository(db)
    flow = repo.get_live(flow_id, current_user.org_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    step_repo = FlowStepRepository(db)
    steps = step_repo.list_by_flow(flow_id, current_user.org_id)
    result = _flow_out(flow, repo)
    result["steps"] = [_step_out(s) for s in steps]
    return result


@router.put("/{flow_id}", dependencies=[Depends(require_role("TESTER"))])
def update_flow(
    flow_id: UUID,
    body: FlowUpdate,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = FlowRepository(db)
    flow = repo.get_live(flow_id, current_user.org_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    kwargs = {k: v for k, v in body.model_dump(exclude={"expected_version"}).items() if v is not None}
    flow = repo.update(flow, current_user.id, body.expected_version, **kwargs)
    db.commit()
    db.refresh(flow)
    return _flow_out(flow, repo)


@router.delete("/{flow_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role("TESTER"))])
def delete_flow(
    flow_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = FlowRepository(db)
    flow = repo.get_live(flow_id, current_user.org_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    repo.soft_delete(flow, current_user.id)
    db.commit()


@router.post("/{flow_id}/duplicate", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_role("TESTER"))])
def duplicate_flow(
    flow_id: UUID,
    body: FlowDuplicate,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = FlowRepository(db)
    flow = repo.get_live(flow_id, current_user.org_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    new_flow = repo.duplicate(flow, current_user.id, body.new_name)
    db.commit()
    db.refresh(new_flow)
    return _flow_out(new_flow, repo)


# ── Flow Steps ────────────────────────────────────────────────────────────────

@router.post("/{flow_id}/steps", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_role("TESTER"))])
def create_flow_step(
    flow_id: UUID,
    body: FlowStepCreate,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    flow_repo = FlowRepository(db)
    flow = flow_repo.get_live(flow_id, current_user.org_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    step_repo = FlowStepRepository(db)
    step = step_repo.create(
        flow=flow,
        actor_id=current_user.id,
        flow_repo=flow_repo,
        **body.model_dump(exclude_none=True),
    )
    db.commit()
    db.refresh(step)
    return _step_out(step)


@router.put("/{flow_id}/steps/reorder", dependencies=[Depends(require_role("TESTER"))])
def reorder_flow_steps(
    flow_id: UUID,
    body: ReorderRequest,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    flow_repo = FlowRepository(db)
    flow = flow_repo.get_live(flow_id, current_user.org_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    step_repo = FlowStepRepository(db)
    steps = step_repo.reorder(flow, body.step_ids, current_user.id, flow_repo)
    db.commit()
    return [_step_out(s) for s in steps]


@router.put("/steps/{step_id}", dependencies=[Depends(require_role("TESTER"))])
def update_flow_step(
    step_id: UUID,
    body: FlowStepUpdate,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    step_repo = FlowStepRepository(db)
    step = step_repo.get_live(step_id, current_user.org_id)
    if step is None:
        raise HTTPException(status_code=404, detail="Flow step not found")
    flow_repo = FlowRepository(db)
    flow = flow_repo.get_live(step.flow_id, current_user.org_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    kwargs = body.model_dump(exclude_unset=True)
    nullable = {"input_value", "target_url", "description", "page_object_id"}
    if any(v is None and k not in nullable for k, v in kwargs.items()):
        raise HTTPException(422, "Action, flags and timeout cannot be null")
    step = step_repo.update(step, flow, current_user.id, flow_repo, **kwargs)
    db.commit()
    db.refresh(step)
    return _step_out(step)


@router.delete("/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role("TESTER"))])
def delete_flow_step(
    step_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    step_repo = FlowStepRepository(db)
    step = step_repo.get_live(step_id, current_user.org_id)
    if step is None:
        raise HTTPException(status_code=404, detail="Flow step not found")
    flow_repo = FlowRepository(db)
    flow = flow_repo.get_live(step.flow_id, current_user.org_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")
    step_repo.soft_delete(step, flow, current_user.id, flow_repo)
    db.commit()
