"""
db/repositories/environments.py — Phase 3: Environment and EnvironmentVariable repositories.

Key behaviors:
  - version bumps on ANY semantic change (variables, metadata, base_url, tags)
  - Optimistic locking: PUT raises 409 if expected_version != current version
  - Case-insensitive uniqueness of variable keys enforced at write time
  - Tags: normalised to lowercase
  - Soft delete on EnvironmentVariable (not cascade delete)
"""

import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.crypto import encrypt, is_crypto_configured
from app.db.base import utcnow
from app.db.repositories.base import OrgScopedRepository
from app.models.environments import Environment, EnvironmentVariable
from app.models.foundation import AuditEvent


def _utcnow() -> datetime:
    return utcnow()


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


def _audit(db: Session, org_id: UUID, actor_id: Optional[UUID], action: str, entity_id: UUID) -> None:
    ev = AuditEvent(
        org_id=org_id,
        actor_id=actor_id,
        entity_type="environment",
        entity_id=entity_id,
        action=action,
    )
    db.add(ev)


class EnvironmentRepository(OrgScopedRepository[Environment]):
    model = Environment

    def list_all(
        self,
        org_id: UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Environment]:
        stmt = (
            select(Environment)
            .where(Environment.org_id == org_id, Environment.deleted_at.is_(None))
            .order_by(Environment.is_default.desc(), Environment.name)
            .offset(offset).limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def count(self, org_id: UUID) -> int:
        stmt = select(func.count()).select_from(Environment).where(
            Environment.org_id == org_id, Environment.deleted_at.is_(None)
        )
        return self.db.scalar(stmt) or 0

    def get_live(self, env_id: UUID, org_id: UUID) -> Optional[Environment]:
        return self.get(env_id, org_id)

    def create(
        self, org_id: UUID, actor_id: Optional[UUID],
        name: str, description: Optional[str] = None,
        base_url: Optional[str] = None, tags: Optional[list] = None,
        is_default: bool = False,
    ) -> Environment:
        # Pre-check for duplicate name (avoids unhandled UniqueViolation)
        existing = self.db.scalar(
            select(Environment).where(
                Environment.org_id == org_id,
                Environment.name == name,
                Environment.deleted_at.is_(None),
            )
        )
        if existing is not None:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=422,
                detail=f"Environment name '{name}' already exists in this organization",
            )
        env = Environment(
            org_id=org_id,
            name=name,
            description=description,
            base_url=base_url,
            tags=_norm_tags(tags),
            version=1,
            is_default=is_default,
            created_by=actor_id,
        )
        self.db.add(env)
        self.db.flush()
        _audit(self.db, org_id, actor_id, "CREATED", env.id)
        return env

    def update(
        self,
        env: Environment,
        actor_id: Optional[UUID],
        expected_version: int,
        **kwargs,
    ) -> Environment:
        if env.version != expected_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "VERSION_CONFLICT",
                    "current_version": env.version,
                    "submitted_version": expected_version,
                },
            )
        if "tags" in kwargs:
            kwargs["tags"] = _norm_tags(kwargs["tags"])
        for k, v in kwargs.items():
            setattr(env, k, v)
        env.version += 1
        env.updated_by = actor_id
        self.db.flush()
        _audit(self.db, env.org_id, actor_id, "UPDATED", env.id)
        return env

    def soft_delete(self, env: Environment, actor_id: Optional[UUID]) -> Environment:
        now = _utcnow()
        env.deleted_at = now
        env.deleted_by = actor_id
        env.version += 1
        env.updated_by = actor_id
        self.db.flush()
        _audit(self.db, env.org_id, actor_id, "DELETED", env.id)
        return env

    def get_tags(self, env: Environment) -> list:
        if not env.tags:
            return []
        try:
            return json.loads(env.tags)
        except Exception:
            return []


class EnvironmentVariableRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_by_env(self, env_id: UUID, org_id: UUID) -> list[EnvironmentVariable]:
        stmt = (
            select(EnvironmentVariable)
            .where(
                EnvironmentVariable.environment_id == env_id,
                EnvironmentVariable.org_id == org_id,
                EnvironmentVariable.deleted_at.is_(None),
            )
            .order_by(EnvironmentVariable.key)
        )
        return list(self.db.scalars(stmt).all())

    def get_live(self, var_id: UUID, org_id: UUID) -> Optional[EnvironmentVariable]:
        stmt = select(EnvironmentVariable).where(
            EnvironmentVariable.id == var_id,
            EnvironmentVariable.org_id == org_id,
            EnvironmentVariable.deleted_at.is_(None),
        )
        return self.db.scalar(stmt)

    def _check_key_collision(self, env_id: UUID, key: str, exclude_id: Optional[UUID] = None) -> None:
        """Reject keys that differ only by case (case-insensitive uniqueness)."""
        stmt = select(EnvironmentVariable).where(
            EnvironmentVariable.environment_id == env_id,
            EnvironmentVariable.deleted_at.is_(None),
            EnvironmentVariable.key.ilike(key),
        )
        if exclude_id:
            stmt = stmt.where(EnvironmentVariable.id != exclude_id)
        existing = self.db.scalar(stmt)
        if existing is not None and existing.key != key:
            raise HTTPException(
                status_code=422,
                detail=f"Variable key '{key}' conflicts with existing key '{existing.key}' (case-insensitive collision)",
            )
        if existing is not None and existing.key == key:
            raise HTTPException(status_code=422, detail=f"Variable key '{key}' already exists")

    def create(
        self,
        environment: Environment,
        actor_id: Optional[UUID],
        key: str,
        plaintext_value: str,
        var_type: str = "STRING",
        is_secret: bool = False,
        description: Optional[str] = None,
    ) -> EnvironmentVariable:
        self._check_key_collision(environment.id, key)
        ciphertext, key_id = self._encrypt(plaintext_value)
        var = EnvironmentVariable(
            org_id=environment.org_id,
            environment_id=environment.id,
            key=key,
            value_encrypted=ciphertext,
            key_id=key_id,
            type=var_type,
            is_secret=is_secret,
            description=description,
            created_by=actor_id,
        )
        self.db.add(var)
        self.db.flush()
        # Bump environment version on variable add
        environment.version += 1
        environment.updated_by = actor_id
        self.db.flush()
        return var

    def update(
        self,
        var: EnvironmentVariable,
        environment: Environment,
        actor_id: Optional[UUID],
        plaintext_value: Optional[str] = None,
        var_type: Optional[str] = None,
        is_secret: Optional[bool] = None,
        description: Optional[str] = None,
    ) -> EnvironmentVariable:
        if plaintext_value is not None:
            ciphertext, key_id = self._encrypt(plaintext_value)
            var.value_encrypted = ciphertext
            var.key_id = key_id
        if var_type is not None:
            var.type = var_type
        if is_secret is not None:
            var.is_secret = is_secret
        if description is not None:
            var.description = description
        self.db.flush()
        environment.version += 1
        environment.updated_by = actor_id
        self.db.flush()
        return var

    def soft_delete(
        self, var: EnvironmentVariable, environment: Environment, actor_id: Optional[UUID]
    ) -> EnvironmentVariable:
        var.deleted_at = _utcnow()
        self.db.flush()
        environment.version += 1
        environment.updated_by = actor_id
        self.db.flush()
        return var

    @staticmethod
    def _encrypt(plaintext: str) -> tuple[str, str]:
        """Encrypt value or fall back to plain storage when no keys configured."""
        if is_crypto_configured():
            return encrypt(plaintext)
        # Test/dev fallback — no keys configured
        from app.core.config import settings
        return plaintext, settings.VARIABLE_ENCRYPTION_ACTIVE_KEY_ID
