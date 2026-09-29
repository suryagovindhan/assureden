"""Append-only authored flow history. Locators are resolved when queueing a run."""
from copy import deepcopy
from sqlalchemy import select
from app.models.flows import Flow, FlowStep
from app.models.foundation import AssetRevision

STEP_FIELDS = ("id", "version", "position", "action", "description", "input_value",
               "target_url", "timeout_ms", "is_optional", "is_enabled", "page_object_id")


def authored_snapshot(db, flow):
    steps = db.scalars(select(FlowStep).where(
        FlowStep.flow_id == flow.id, FlowStep.org_id == flow.org_id,
        FlowStep.deleted_at.is_(None)).order_by(FlowStep.position)).all()
    return {"name": flow.name, "kind": flow.kind, "description": flow.description, "tags": flow.tags,
            "checksum": flow.checksum, "steps": [
                {key: str(getattr(s, key)) if key in ("id", "page_object_id")
                 and getattr(s, key) is not None else getattr(s, key)
                 for key in STEP_FIELDS} for s in steps]}


def get_revision(db, flow, version):
    row = db.scalar(select(AssetRevision).where(
        AssetRevision.org_id == flow.org_id, AssetRevision.asset_type == "Flow",
        AssetRevision.asset_id == flow.id, AssetRevision.revision == version))
    if row:
        return deepcopy(row.snapshot)
    # Legacy flows only have their current content; never invent older history.
    if flow.version == version:
        return authored_snapshot(db, flow)
    raise ValueError("Pinned flow version is unavailable")


def preserve_revision(db, flow):
    db.flush()
    exists = db.scalar(select(AssetRevision.id).where(
        AssetRevision.org_id == flow.org_id, AssetRevision.asset_type == "Flow",
        AssetRevision.asset_id == flow.id, AssetRevision.revision == flow.version))
    if not exists:
        db.add(AssetRevision(org_id=flow.org_id, asset_type="Flow", asset_id=flow.id,
                            revision=flow.version, snapshot=authored_snapshot(db, flow),
                            created_by=flow.updated_by or flow.created_by))
        db.flush()


def lock_and_preserve(db, flow):
    db.refresh(flow, with_for_update=True)
    if flow.deleted_at is not None:
        from fastapi import HTTPException
        raise HTTPException(404, "Flow not found")
    preserve_revision(db, flow)
