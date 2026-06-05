"""
api/users/router.py — User CRUD (org-scoped)
"""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentUser, require_role
from app.core.security import hash_password
from app.db.session import get_db
from app.db.repositories.foundation import UserRepository, AuditEventRepository

router = APIRouter(prefix="/users", tags=["users"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str = "TESTER"


class UserUpdate(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: UUID
    org_id: UUID
    username: str
    email: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[UserResponse])
def list_users(
    offset: int = 0,
    limit: int = 50,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = UserRepository(db)
    return repo.list(current_user.org_id, offset=offset, limit=limit)


@router.post("/", response_model=UserResponse, dependencies=[Depends(require_role("ADMIN"))])
def create_user(
    body: UserCreate,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = UserRepository(db)
    if repo.get_by_email(body.email, current_user.org_id):
        raise HTTPException(status_code=400, detail="Email already registered in this org")
    if repo.get_by_username(body.username, current_user.org_id):
        raise HTTPException(status_code=400, detail="Username already taken in this org")

    user = repo.create_user(
        org_id=current_user.org_id,
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    db.commit()
    db.refresh(user)

    AuditEventRepository(db).write(
        org_id=current_user.org_id,
        entity_type="User",
        entity_id=user.id,
        action="CREATED",
        actor_id=current_user.id,
    )
    db.commit()
    return user


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = UserRepository(db)
    user = repo.get(user_id, current_user.org_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserResponse, dependencies=[Depends(require_role("ADMIN"))])
def update_user(
    user_id: UUID,
    body: UserUpdate,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = UserRepository(db)
    user = repo.get(user_id, current_user.org_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if body.username is not None:
        user.username = body.username
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active

    db.commit()
    db.refresh(user)

    AuditEventRepository(db).write(
        org_id=current_user.org_id,
        entity_type="User",
        entity_id=user.id,
        action="UPDATED",
        actor_id=current_user.id,
    )
    db.commit()
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_role("ADMIN"))])
def delete_user(
    user_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = UserRepository(db)
    user = repo.soft_delete(user_id, current_user.org_id, current_user.id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    db.commit()

    AuditEventRepository(db).write(
        org_id=current_user.org_id,
        entity_type="User",
        entity_id=user_id,
        action="DELETED",
        actor_id=current_user.id,
    )
    db.commit()
