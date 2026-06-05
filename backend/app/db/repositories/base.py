"""
db/repositories/base.py

OrgScopedRepository is the data-access contract for every entity in the system.
No route handler or service may query the DB directly — all access goes through
a repository that extends this class.

Invariants enforced on every query:
  1. org_id = current_user.org_id            (tenant boundary)
  2. deleted_at IS NULL                      (soft-delete exclusion)
"""

from typing import Generic, Optional, Type, TypeVar
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db.base import Base, utcnow

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Pure CRUD — no org or soft-delete enforcement. Use only for entities
    that genuinely have no org_id (e.g. Permission, which is global)."""

    model: Type[ModelT]

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, id: UUID) -> Optional[ModelT]:
        return self.db.get(self.model, id)

    def create(self, **kwargs) -> ModelT:
        obj = self.model(**kwargs)
        self.db.add(obj)
        self.db.flush()
        return obj

    def save(self) -> None:
        self.db.flush()

    def commit(self) -> None:
        self.db.commit()

    def refresh(self, obj: ModelT) -> ModelT:
        self.db.refresh(obj)
        return obj


class OrgScopedRepository(BaseRepository[ModelT]):
    """
    Base for every entity that carries org_id + deleted_at.
    All reads automatically inject:
      WHERE org_id = :org_id AND deleted_at IS NULL

    Never trust frontend filtering.
    Never bypass this class for org-scoped data.
    """

    def get(self, id: UUID, org_id: UUID) -> Optional[ModelT]:
        """Fetch a single record — returns None if not found, wrong org, or soft-deleted."""
        stmt = (
            select(self.model)
            .where(
                self.model.id == id,
                self.model.org_id == org_id,
                self.model.deleted_at.is_(None),
            )
        )
        return self.db.scalar(stmt)

    def list(
        self,
        org_id: UUID,
        offset: int = 0,
        limit: int = 50,
        **filters,
    ) -> list[ModelT]:
        """List records for an org — soft-deleted records never appear."""
        stmt = (
            select(self.model)
            .where(
                self.model.org_id == org_id,
                self.model.deleted_at.is_(None),
            )
        )
        for attr, value in filters.items():
            stmt = stmt.where(getattr(self.model, attr) == value)
        stmt = stmt.offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def count(self, org_id: UUID, **filters) -> int:
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(
                self.model.org_id == org_id,
                self.model.deleted_at.is_(None),
            )
        )
        for attr, value in filters.items():
            stmt = stmt.where(getattr(self.model, attr) == value)
        return self.db.scalar(stmt) or 0

    def soft_delete(self, id: UUID, org_id: UUID, deleted_by: UUID) -> Optional[ModelT]:
        """Soft-delete — sets deleted_at and deleted_by. Never issues SQL DELETE."""
        obj = self.get(id, org_id)
        if obj is None:
            return None
        obj.deleted_at = utcnow()
        obj.deleted_by = deleted_by
        self.db.flush()
        return obj

    def restore(self, id: UUID, org_id: UUID) -> Optional[ModelT]:
        """Restore a soft-deleted record by clearing deleted_at."""
        stmt = (
            select(self.model)
            .where(
                self.model.id == id,
                self.model.org_id == org_id,
                self.model.deleted_at.is_not(None),
            )
        )
        obj = self.db.scalar(stmt)
        if obj is None:
            return None
        obj.deleted_at = None
        obj.deleted_by = None
        self.db.flush()
        return obj
