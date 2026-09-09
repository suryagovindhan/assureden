"""
api/environments/router.py — Phase 3: Environments and Variables API
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentUser, require_role
from app.db.session import get_db
from app.db.repositories.environments import EnvironmentRepository, EnvironmentVariableRepository

router = APIRouter(prefix="/environments", tags=["environments"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class EnvCreate(BaseModel):
    name: str
    description: Optional[str] = None
    base_url: Optional[str] = None
    tags: Optional[list[str]] = None
    is_default: bool = False


class EnvUpdate(BaseModel):
    expected_version: int
    name: Optional[str] = None
    description: Optional[str] = None
    base_url: Optional[str] = None
    tags: Optional[list[str]] = None
    is_default: Optional[bool] = None


class VarCreate(BaseModel):
    key: str
    value: str          # plaintext — encrypted at repository layer
    type: str = "STRING"
    is_secret: bool = False
    description: Optional[str] = None


class VarUpdate(BaseModel):
    value: Optional[str] = None
    type: Optional[str] = None
    is_secret: Optional[bool] = None
    description: Optional[str] = None


def _env_out(env, env_repo: EnvironmentRepository) -> dict:
    return {
        "id":          str(env.id),
        "org_id":      str(env.org_id),
        "name":        env.name,
        "description": env.description,
        "base_url":    env.base_url,
        "tags":        env_repo.get_tags(env),
        "version":     env.version,
        "is_default":  env.is_default,
        "created_at":  env.created_at.isoformat(),
        "updated_at":  env.updated_at.isoformat(),
        "created_by":  str(env.created_by) if env.created_by else None,
        "updated_by":  str(env.updated_by) if env.updated_by else None,
    }


def _var_out(var) -> dict:
    return {
        "id":             str(var.id),
        "environment_id": str(var.environment_id),
        "key":            var.key,
        "value":          "****" if var.is_secret else "****",   # never return plaintext
        "display_value":  None if var.is_secret else None,       # resolved at runtime
        "type":           var.type,
        "is_secret":      var.is_secret,
        "description":    var.description,
        "key_id":         var.key_id,
        "created_at":     var.created_at.isoformat(),
    }


# ── Environment CRUD ─────────────────────────────────────────────────────────

@router.get("/")
def list_environments(
    offset: int = 0, limit: int = 100,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = EnvironmentRepository(db)
    envs = repo.list_all(current_user.org_id, offset=offset, limit=limit)
    total = repo.count(current_user.org_id)
    return {"items": [_env_out(e, repo) for e in envs], "total": total}


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_environment(
    body: EnvCreate,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    from sqlalchemy.exc import IntegrityError
    repo = EnvironmentRepository(db)
    env = repo.create(
        org_id=current_user.org_id,
        actor_id=current_user.id,
        name=body.name,
        description=body.description,
        base_url=body.base_url,
        tags=body.tags,
        is_default=body.is_default,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail=f"Environment name '{body.name}' already exists in this organization",
        )
    db.refresh(env)
    return _env_out(env, repo)


@router.get("/{env_id}")
def get_environment(
    env_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = EnvironmentRepository(db)
    env = repo.get_live(env_id, current_user.org_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    return _env_out(env, repo)


@router.put("/{env_id}")
def update_environment(
    env_id: UUID,
    body: EnvUpdate,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = EnvironmentRepository(db)
    env = repo.get_live(env_id, current_user.org_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    kwargs = {k: v for k, v in body.model_dump(exclude={"expected_version"}).items() if v is not None}
    env = repo.update(env, current_user.id, body.expected_version, **kwargs)
    db.commit()
    db.refresh(env)
    return _env_out(env, repo)


@router.delete("/{env_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_environment(
    env_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = EnvironmentRepository(db)
    env = repo.get_live(env_id, current_user.org_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    repo.soft_delete(env, current_user.id)
    db.commit()


# ── Variables ────────────────────────────────────────────────────────────────

@router.get("/{env_id}/variables")
def list_variables(
    env_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    env_repo = EnvironmentRepository(db)
    env = env_repo.get_live(env_id, current_user.org_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    var_repo = EnvironmentVariableRepository(db)
    vars_ = var_repo.list_by_env(env_id, current_user.org_id)
    return [_var_out(v) for v in vars_]


@router.post("/{env_id}/variables", status_code=status.HTTP_201_CREATED)
def create_variable(
    env_id: UUID,
    body: VarCreate,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    env_repo = EnvironmentRepository(db)
    env = env_repo.get_live(env_id, current_user.org_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    var_repo = EnvironmentVariableRepository(db)
    var = var_repo.create(
        environment=env,
        actor_id=current_user.id,
        key=body.key,
        plaintext_value=body.value,
        var_type=body.type,
        is_secret=body.is_secret,
        description=body.description,
    )
    db.commit()
    db.refresh(var)
    return _var_out(var)


@router.put("/{env_id}/variables/{var_id}")
def update_variable(
    env_id: UUID,
    var_id: UUID,
    body: VarUpdate,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    env_repo = EnvironmentRepository(db)
    env = env_repo.get_live(env_id, current_user.org_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    var_repo = EnvironmentVariableRepository(db)
    var = var_repo.get_live(var_id, current_user.org_id)
    if var is None or var.environment_id != env_id:
        raise HTTPException(status_code=404, detail="Variable not found")
    var = var_repo.update(
        var=var, environment=env, actor_id=current_user.id,
        plaintext_value=body.value,
        var_type=body.type, is_secret=body.is_secret, description=body.description,
    )
    db.commit()
    db.refresh(var)
    return _var_out(var)


@router.delete("/{env_id}/variables/{var_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variable(
    env_id: UUID,
    var_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    env_repo = EnvironmentRepository(db)
    env = env_repo.get_live(env_id, current_user.org_id)
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")
    var_repo = EnvironmentVariableRepository(db)
    var = var_repo.get_live(var_id, current_user.org_id)
    if var is None or var.environment_id != env_id:
        raise HTTPException(status_code=404, detail="Variable not found")
    var_repo.soft_delete(var, env, current_user.id)
    db.commit()
