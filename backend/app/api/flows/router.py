"""
api/flows/router.py — Phase 3: Reusable Flows API
"""

import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentUser
from app.db.session import get_db
from app.db.repositories.flows import FlowRepository, FlowStepRepository

router = APIRouter(prefix="/flows", tags=["flows"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class FlowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class FlowUpdate(BaseModel):
    expected_version: int
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class FlowDuplicate(BaseModel):
    new_name: str


class FlowStepCreate(BaseModel):
    action: str
    input_value: Optional[str] = None
    target_url: Optional[str] = None
    description: Optional[str] = None
    timeout_ms: int = 30000
    is_optional: bool = False
    is_enabled: bool = True
    page_object_id: Optional[UUID] = None


class FlowStepUpdate(BaseModel):
    action: Optional[str] = None
    input_value: Optional[str] = None
    target_url: Optional[str] = None
    description: Optional[str] = None
    timeout_ms: Optional[int] = None
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


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_flow(
    body: FlowCreate,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    from sqlalchemy.exc import IntegrityError
    repo = FlowRepository(db)
    flow = repo.create(
        org_id=current_user.org_id,
        actor_id=current_user.id,
        name=body.name,
        description=body.description,
        tags=body.tags,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail=f"Flow name '{body.name}' already exists in this organization",
        )
    db.refresh(flow)
    return _flow_out(flow, repo)


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


@router.put("/{flow_id}")
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


@router.delete("/{flow_id}", status_code=status.HTTP_204_NO_CONTENT)
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


@router.post("/{flow_id}/duplicate", status_code=status.HTTP_201_CREATED)
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

@router.post("/{flow_id}/steps", status_code=status.HTTP_201_CREATED)
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


@router.put("/{flow_id}/steps/reorder")
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


@router.put("/steps/{step_id}")
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
    kwargs = {k: v for k, v in body.model_dump().items() if v is not None}
    step = step_repo.update(step, flow, current_user.id, flow_repo, **kwargs)
    db.commit()
    db.refresh(step)
    return _step_out(step)


@router.delete("/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
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
