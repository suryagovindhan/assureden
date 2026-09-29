"""Transactional promotion of reviewed recordings into canonical test cases."""
import json
from fastapi import HTTPException
from sqlalchemy import select
from app.models.drafts import DraftAsset
from app.models.object_repository import Page, Module, Application, PageObject
from app.models.test_cases import TestCase, TestStep
from app.models.foundation import AssetRevision
from app.models.flows import Flow, FlowStep
from app.db.repositories.flows import _compute_checksum
from app.services.flow_revisions import preserve_revision
from app.db.repositories.foundation import AuditEventRepository


def get_draft(db, draft_id, org_id, *, lock=False):
    query = select(DraftAsset).where(DraftAsset.id == draft_id, DraftAsset.org_id == org_id)
    draft = db.scalar(query.with_for_update() if lock else query)
    if draft is None:
        raise HTTPException(404, "Draft not found")
    return draft


def check_version(draft, version):
    if draft.version != version:
        raise HTTPException(409, "Draft changed; reload it before continuing")


def promote(db, draft, request, user):
    check_version(draft, request.expected_version)
    existing = draft.promoted_flow_id if request.target in ("FLOW", "BUSINESS_ACTION") else draft.promoted_case_id
    if existing:
        if draft.promoted_flow_id:
            asset = db.get(Flow, existing)
            if asset.kind != request.target:
                raise HTTPException(409, "Draft was already promoted to another asset type")
        return existing
    if draft.status != "DRAFT":
        raise HTTPException(409, "Draft was already promoted to another asset type")
    page = db.get(Page, request.page_id)
    module = db.get(Module, page.module_id) if page else None
    application = db.get(Application, module.application_id) if module else None
    if any(x is None or x.org_id != user.org_id or x.deleted_at is not None
           for x in (page, module, application)):
        raise HTTPException(422, "Choose an available page in your organization")
    if request.target in ("FLOW", "BUSINESS_ACTION"):
        if db.scalar(select(Flow.id).where(Flow.org_id == user.org_id, Flow.name == draft.name, Flow.deleted_at.is_(None))):
            raise HTTPException(409, "A flow with this name already exists; rename the draft")
        case = Flow(org_id=user.org_id, name=draft.name, created_by=user.id, kind=request.target)
    else:
        case = TestCase(org_id=user.org_id, application_id=application.id, name=draft.name,
                        created_by=user.id, status="DRAFT")
    db.add(case); db.flush()
    objects = {}
    for position, recorded in enumerate(draft.recording["steps"], 1):
        object_id = None
        if recorded["action"] != "NAVIGATE":
            locators = recorded["locators"]
            key = json.dumps(locators, sort_keys=True)
            if key not in objects:
                obj = PageObject(org_id=user.org_id, page_id=page.id,
                    name=f"Recorded element {position} ({str(draft.id)[:8]})",
                    object_type={"TYPE": "INPUT", "SELECT": "DROPDOWN", "CHECK": "CHECKBOX", "UNCHECK": "CHECKBOX"}.get(recorded["action"], "CONTAINER"),
                    locators=locators, created_by=user.id)
                db.add(obj); db.flush()
                objects[key] = obj.id
            object_id = objects[key]
        step_type = FlowStep if request.target in ("FLOW", "BUSINESS_ACTION") else TestStep
        parent = {"flow_id": case.id} if request.target in ("FLOW", "BUSINESS_ACTION") else {"test_case_id": case.id}
        db.add(step_type(org_id=user.org_id, **parent, position=position,
            action=recorded["action"], page_object_id=object_id,
            input_value=recorded["input_value"] if recorded["action"] != "NAVIGATE" else None,
            target_url=recorded["input_value"] if recorded["action"] == "NAVIGATE" else None,
            created_by=user.id))
    if request.target in ("FLOW", "BUSINESS_ACTION"):
        db.flush()
        case.checksum = _compute_checksum(db, case.id)
        preserve_revision(db, case)
        draft.promoted_flow_id = case.id
    else:
        draft.promoted_case_id = case.id
    target_key = "flow_id" if request.target in ("FLOW", "BUSINESS_ACTION") else "test_case_id"
    db.add(AssetRevision(org_id=user.org_id, asset_type="DraftAsset", asset_id=draft.id,
        revision=draft.version, snapshot={"recording": draft.recording, target_key: str(case.id)},
        created_by=user.id, change_summary=f"Promoted recording to {request.target}"))
    draft.status = "PROMOTED"
    AuditEventRepository(db).write(user.org_id, "DraftAsset", draft.id, "PROMOTED", actor_id=user.id)
    return case.id
