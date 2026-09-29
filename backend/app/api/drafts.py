import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.dependencies import CurrentUser, require_role
from app.db.session import get_db
from app.db.repositories.foundation import AuditEventRepository
from app.models.drafts import DraftAsset
from app.schemas.drafts import Recording, DraftUpdate, PromoteDraft
from app.services.drafts import get_draft, check_version, promote

router = APIRouter(prefix="/drafts", tags=["Recorder drafts"])


def out(draft):
    return {"id": str(draft.id), "name": draft.name, "version": draft.version,
            "status": draft.status, "recording": draft.recording,
            "promoted_case_id": str(draft.promoted_case_id) if draft.promoted_case_id else None,
            "promoted_flow_id": str(draft.promoted_flow_id) if draft.promoted_flow_id else None}


def content(body):
    data = body.model_dump(mode="json", exclude={"expected_version"})
    if len(json.dumps(data).encode()) > 2_000_000:
        raise HTTPException(413, "Recording exceeds 2 MB")
    return data


@router.get("")
def list_drafts(current_user: CurrentUser, db: Session = Depends(get_db)):
    drafts = db.scalars(select(DraftAsset).where(DraftAsset.org_id == current_user.org_id)
                       .order_by(DraftAsset.created_at.desc()).limit(100)).all()
    return [out(d) for d in drafts]


@router.post("", status_code=201, dependencies=[Depends(require_role("TESTER"))])
def create(body: Recording, current_user: CurrentUser, db: Session = Depends(get_db)):
    draft = DraftAsset(org_id=current_user.org_id, name=body.name,
                       recording=content(body), created_by=current_user.id)
    db.add(draft); db.flush()
    AuditEventRepository(db).write(current_user.org_id, "DraftAsset", draft.id, "CREATED", actor_id=current_user.id)
    db.commit(); db.refresh(draft)
    return out(draft)


@router.put("/{draft_id}", dependencies=[Depends(require_role("TESTER"))])
def update(draft_id: UUID, body: DraftUpdate, current_user: CurrentUser, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id, current_user.org_id, lock=True)
    check_version(draft, body.expected_version)
    if draft.status != "DRAFT":
        raise HTTPException(409, "Promoted drafts cannot be edited")
    draft.recording = content(body); draft.name = body.name; draft.version += 1
    AuditEventRepository(db).write(current_user.org_id, "DraftAsset", draft.id, "UPDATED", actor_id=current_user.id)
    db.commit(); db.refresh(draft)
    return out(draft)


@router.post("/{draft_id}/promote", dependencies=[Depends(require_role("TESTER"))])
def promote_draft(draft_id: UUID, body: PromoteDraft, current_user: CurrentUser, db: Session = Depends(get_db)):
    draft = get_draft(db, draft_id, current_user.org_id, lock=True)
    case_id = promote(db, draft, body, current_user)
    db.commit()
    return {"flow_id" if body.target in ("FLOW", "BUSINESS_ACTION") else "test_case_id": str(case_id)}
