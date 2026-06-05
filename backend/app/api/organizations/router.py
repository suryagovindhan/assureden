"""
api/organizations/router.py — Organization CRUD (ADMIN only)
"""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentUser, require_role
from app.db.session import get_db
from app.db.repositories.foundation import OrganizationRepository, AuditEventRepository

router = APIRouter(prefix="/organizations", tags=["organizations"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class OrgCreate(BaseModel):
    name: str
    slug: str


class OrgResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    is_active: bool

    model_config = {"from_attributes": True}


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=OrgResponse, dependencies=[Depends(require_role("ADMIN"))])
def create_org(body: OrgCreate, db: Session = Depends(get_db), current_user: CurrentUser = None):
    repo = OrganizationRepository(db)
    if repo.get_by_slug(body.slug):
        raise HTTPException(status_code=400, detail="Slug already taken")
    org = repo.create_org(name=body.name, slug=body.slug)
    db.commit()
    db.refresh(org)

    AuditEventRepository(db).write(
        org_id=org.id,
        entity_type="Organization",
        entity_id=org.id,
        action="CREATED",
        actor_id=current_user.id,
    )
    db.commit()
    return org


@router.get("/{org_id}", response_model=OrgResponse)
def get_org(org_id: UUID, current_user: CurrentUser = None, db: Session = Depends(get_db)):
    if org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    repo = OrganizationRepository(db)
    org = repo.get(org_id, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org
