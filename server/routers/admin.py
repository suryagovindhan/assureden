from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from server.database import get_db
from server.models import User, Application, TestModule
from server.security import get_password_hash
from server.routers.auth import get_current_user

router = APIRouter(prefix="/api/admin", tags=["Admin"])

# ──────────────────────────────────────────────────────
# USERS CRUD
# ──────────────────────────────────────────────────────
class UserCreate(BaseModel):
    username: str
    email: str
    role: str = "TESTER"
    password: str

class UserUpdate(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    users = db.query(User).all()
    return [
        {
            "id": str(u.id), "username": u.username, "email": u.email,
            "role": u.role, "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None
        }
        for u in users
    ]

@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    existing = db.query(User).filter(
        (User.username == payload.username) | (User.email == payload.email)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already exists.")
    new_user = User(
        username=payload.username,
        email=payload.email,
        role=payload.role,
        hashed_password=get_password_hash(payload.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"id": str(new_user.id), "username": new_user.username, "role": new_user.role}

@router.patch("/users/{user_id}")
def update_user(user_id: str, payload: UserUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if payload.email is not None:
        user.email = payload.email
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    return {"status": "updated"}

@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if str(user.id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")
    db.delete(user)
    db.commit()

# ──────────────────────────────────────────────────────
# APPLICATIONS CRUD
# ──────────────────────────────────────────────────────
class AppCreate(BaseModel):
    name: str
    app_type: str
    vendor: Optional[str] = None
    base_url: Optional[str] = None
    description: Optional[str] = None

class AppUpdate(BaseModel):
    name: Optional[str] = None
    app_type: Optional[str] = None
    vendor: Optional[str] = None
    base_url: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/applications")
def list_applications(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    apps = db.query(Application).all()
    return [
        {
            "id": str(a.id), "name": a.name, "app_type": a.app_type,
            "vendor": a.vendor, "base_url": a.base_url,
            "description": a.description, "is_active": a.is_active,
            "created_at": a.created_at.isoformat() if a.created_at else None
        }
        for a in apps
    ]

@router.post("/applications", status_code=status.HTTP_201_CREATED)
def create_application(payload: AppCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    existing = db.query(Application).filter(Application.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Application name already exists.")
    app = Application(**payload.model_dump())
    db.add(app)
    db.commit()
    db.refresh(app)
    return {"id": str(app.id), "name": app.name}

@router.patch("/applications/{app_id}")
def update_application(app_id: str, payload: AppUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(app, field, value)
    db.commit()
    return {"status": "updated"}

@router.delete("/applications/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(app_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    db.delete(app)
    db.commit()

# ──────────────────────────────────────────────────────
# TEST MODULES CRUD
# ──────────────────────────────────────────────────────
class ModuleCreate(BaseModel):
    domain: str          # PAM | IAM
    name: str
    action_key: str
    description: Optional[str] = None
    url_path: Optional[str] = None

class ModuleUpdate(BaseModel):
    domain: Optional[str] = None
    name: Optional[str] = None
    action_key: Optional[str] = None
    description: Optional[str] = None
    url_path: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/modules")
def list_modules(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    mods = db.query(TestModule).order_by(TestModule.domain, TestModule.name).all()
    return [
        {
            "id": str(m.id), "domain": m.domain, "name": m.name,
            "action_key": m.action_key, "description": m.description,
            "url_path": m.url_path, "is_active": m.is_active,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
        for m in mods
    ]

@router.post("/modules", status_code=status.HTTP_201_CREATED)
def create_module(payload: ModuleCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    existing = db.query(TestModule).filter(TestModule.action_key == payload.action_key).first()
    if existing:
        raise HTTPException(status_code=400, detail="Action key already exists.")
    mod = TestModule(**payload.model_dump())
    db.add(mod)
    db.commit()
    db.refresh(mod)
    return {"id": str(mod.id), "name": mod.name, "action_key": mod.action_key}

@router.patch("/modules/{mod_id}")
def update_module(mod_id: str, payload: ModuleUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    mod = db.query(TestModule).filter(TestModule.id == mod_id).first()
    if not mod:
        raise HTTPException(status_code=404, detail="Module not found.")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(mod, field, value)
    db.commit()
    return {"status": "updated"}

@router.delete("/modules/{mod_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_module(mod_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    mod = db.query(TestModule).filter(TestModule.id == mod_id).first()
    if not mod:
        raise HTTPException(status_code=404, detail="Module not found.")
    db.delete(mod)
    db.commit()
