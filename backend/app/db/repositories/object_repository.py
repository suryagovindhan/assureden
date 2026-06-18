"""
db/repositories/object_repository.py — Phase 1 Object Repository repositories

All repositories extend OrgScopedRepository, which enforces:
  1. org_id = current_user.org_id   (tenant boundary)
  2. deleted_at IS NULL             (soft-delete exclusion)

Cascade visibility:
  Soft-deleting a parent hides all children automatically through repository queries
  that join/filter through the parent's deleted_at. No DB-level CASCADE is used.

Keyword search:
  Uses ILIKE on name + search_keywords::text (cast JSON to string).
  GIN index deferred to Phase 7 when PageObjectLocator table introduced.
  Includes JOIN path for Application/Module/Page names — no N+1 in search results.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select, or_, cast, Text, func
from sqlalchemy.orm import Session, aliased

from app.db.repositories.base import OrgScopedRepository
from app.models.object_repository import (
    Application, Module, Page, PageObject, PageObjectSnapshot,
)


# ── Application ───────────────────────────────────────────────────────────────

class ApplicationRepository(OrgScopedRepository[Application]):
    model = Application

    def get_by_name(self, name: str, org_id: UUID) -> Optional[Application]:
        stmt = select(Application).where(
            Application.org_id == org_id,
            Application.name == name,
            Application.deleted_at.is_(None),
        )
        return self.db.scalar(stmt)


# ── Module ────────────────────────────────────────────────────────────────────

class ModuleRepository(OrgScopedRepository[Module]):
    model = Module

    def list_by_application(
        self,
        application_id: UUID,
        org_id: UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Module]:
        """
        Returns modules whose parent Application is also not deleted.
        Cascade visibility: if Application is soft-deleted, no modules returned.
        """
        stmt = (
            select(Module)
            .join(Application, Module.application_id == Application.id)
            .where(
                Module.org_id == org_id,
                Module.application_id == application_id,
                Module.deleted_at.is_(None),
                Application.deleted_at.is_(None),  # cascade check
            )
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def count_by_application(self, application_id: UUID, org_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Module)
            .join(Application, Module.application_id == Application.id)
            .where(
                Module.org_id == org_id,
                Module.application_id == application_id,
                Module.deleted_at.is_(None),
                Application.deleted_at.is_(None),
            )
        )
        return self.db.scalar(stmt) or 0

    def get_with_app_check(self, module_id: UUID, org_id: UUID) -> Optional[Module]:
        """Fetch module only if parent application is also live."""
        stmt = (
            select(Module)
            .join(Application, Module.application_id == Application.id)
            .where(
                Module.id == module_id,
                Module.org_id == org_id,
                Module.deleted_at.is_(None),
                Application.deleted_at.is_(None),
            )
        )
        return self.db.scalar(stmt)


# ── Page ──────────────────────────────────────────────────────────────────────

class PageRepository(OrgScopedRepository[Page]):
    model = Page

    def list_by_module(
        self,
        module_id: UUID,
        org_id: UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Page]:
        """
        Cascade check: Module AND its parent Application must both be live.
        """
        stmt = (
            select(Page)
            .join(Module, Page.module_id == Module.id)
            .join(Application, Module.application_id == Application.id)
            .where(
                Page.org_id == org_id,
                Page.module_id == module_id,
                Page.deleted_at.is_(None),
                Module.deleted_at.is_(None),
                Application.deleted_at.is_(None),
            )
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def count_by_module(self, module_id: UUID, org_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Page)
            .join(Module, Page.module_id == Module.id)
            .join(Application, Module.application_id == Application.id)
            .where(
                Page.org_id == org_id,
                Page.module_id == module_id,
                Page.deleted_at.is_(None),
                Module.deleted_at.is_(None),
                Application.deleted_at.is_(None),
            )
        )
        return self.db.scalar(stmt) or 0

    def get_with_hierarchy_check(self, page_id: UUID, org_id: UUID) -> Optional[Page]:
        """Fetch page only if all ancestors (Module, Application) are live."""
        stmt = (
            select(Page)
            .join(Module, Page.module_id == Module.id)
            .join(Application, Module.application_id == Application.id)
            .where(
                Page.id == page_id,
                Page.org_id == org_id,
                Page.deleted_at.is_(None),
                Module.deleted_at.is_(None),
                Application.deleted_at.is_(None),
            )
        )
        return self.db.scalar(stmt)


# ── PageObject ────────────────────────────────────────────────────────────────

class PageObjectRepository(OrgScopedRepository[PageObject]):
    model = PageObject

    def list_by_page(
        self,
        page_id: UUID,
        org_id: UUID,
        offset: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
    ) -> list[PageObject]:
        """
        Cascade check: Page, Module, and Application must all be live.
        """
        stmt = (
            select(PageObject)
            .join(Page, PageObject.page_id == Page.id)
            .join(Module, Page.module_id == Module.id)
            .join(Application, Module.application_id == Application.id)
            .where(
                PageObject.org_id == org_id,
                PageObject.page_id == page_id,
                PageObject.deleted_at.is_(None),
                Page.deleted_at.is_(None),
                Module.deleted_at.is_(None),
                Application.deleted_at.is_(None),
            )
        )
        if status:
            stmt = stmt.where(PageObject.status == status)
        stmt = stmt.offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def get_with_hierarchy_check(self, po_id: UUID, org_id: UUID) -> Optional[PageObject]:
        """Fetch a PageObject only if the full ancestor chain is live."""
        stmt = (
            select(PageObject)
            .join(Page, PageObject.page_id == Page.id)
            .join(Module, Page.module_id == Module.id)
            .join(Application, Module.application_id == Application.id)
            .where(
                PageObject.id == po_id,
                PageObject.org_id == org_id,
                PageObject.deleted_at.is_(None),
                Page.deleted_at.is_(None),
                Module.deleted_at.is_(None),
                Application.deleted_at.is_(None),
            )
        )
        return self.db.scalar(stmt)

    def search_by_keyword(
        self,
        keyword: str,
        org_id: UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        """
        Full-text ILIKE search across:
          - PageObject.name
          - PageObject.search_keywords (cast JSON → text)

        Returns dicts with full path info (no N+1):
          application_name, module_name, page_name
        Uses single JOIN query.
        """
        q = f"%{keyword}%"
        stmt = (
            select(
                PageObject,
                Page.name.label("page_name"),
                Module.name.label("module_name"),
                Application.name.label("application_name"),
                Application.id.label("application_id"),
                Module.id.label("module_id"),
                Page.id.label("page_id"),
            )
            .join(Page, PageObject.page_id == Page.id)
            .join(Module, Page.module_id == Module.id)
            .join(Application, Module.application_id == Application.id)
            .where(
                PageObject.org_id == org_id,
                PageObject.deleted_at.is_(None),
                Page.deleted_at.is_(None),
                Module.deleted_at.is_(None),
                Application.deleted_at.is_(None),
                or_(
                    PageObject.name.ilike(q),
                    cast(PageObject.search_keywords, Text).ilike(q),
                ),
            )
            .offset(offset)
            .limit(limit)
        )
        rows = self.db.execute(stmt).all()
        return [
            {
                "id":               str(row.PageObject.id),
                "name":             row.PageObject.name,
                "object_type":      row.PageObject.object_type,
                "page_area":        row.PageObject.page_area,
                "criticality":      row.PageObject.criticality,
                "status":           row.PageObject.status,
                "tags":             row.PageObject.tags,
                "application_id":   str(row.application_id),
                "application_name": row.application_name,
                "module_id":        str(row.module_id),
                "module_name":      row.module_name,
                "page_id":          str(row.page_id),
                "page_name":        row.page_name,
            }
            for row in rows
        ]

    def count_search(self, keyword: str, org_id: UUID) -> int:
        q = f"%{keyword}%"
        stmt = (
            select(func.count())
            .select_from(PageObject)
            .join(Page, PageObject.page_id == Page.id)
            .join(Module, Page.module_id == Module.id)
            .join(Application, Module.application_id == Application.id)
            .where(
                PageObject.org_id == org_id,
                PageObject.deleted_at.is_(None),
                Page.deleted_at.is_(None),
                Module.deleted_at.is_(None),
                Application.deleted_at.is_(None),
                or_(
                    PageObject.name.ilike(q),
                    cast(PageObject.search_keywords, Text).ilike(q),
                ),
            )
        )
        return self.db.scalar(stmt) or 0


# ── PageObjectSnapshot ────────────────────────────────────────────────────────

class PageObjectSnapshotRepository:
    """
    Append-only — no soft delete, no update.
    Uses BaseRepository pattern but does not extend OrgScopedRepository
    because PageObjectSnapshot has no deleted_at column.
    """

    def __init__(self, db: Session):
        self.db = db

    def list_by_page_object(
        self,
        page_object_id: UUID,
        org_id: UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> list[PageObjectSnapshot]:
        stmt = (
            select(PageObjectSnapshot)
            .where(
                PageObjectSnapshot.page_object_id == page_object_id,
                PageObjectSnapshot.org_id == org_id,
            )
            .order_by(PageObjectSnapshot.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def create(
        self,
        org_id: UUID,
        page_object_id: UUID,
        storage_provider: str,
        object_key: str,
        snapshot_metadata: Optional[dict] = None,
        bounding_box: Optional[dict] = None,
        capture_url: Optional[str] = None,
        captured_by: Optional[UUID] = None,
        page_snapshot_provider: Optional[str] = None,
        page_snapshot_key: Optional[str] = None,
    ) -> PageObjectSnapshot:
        snap = PageObjectSnapshot(
            org_id=org_id,
            page_object_id=page_object_id,
            storage_provider=storage_provider,
            object_key=object_key,
            snapshot_metadata=snapshot_metadata,
            bounding_box=bounding_box,
            capture_url=capture_url,
            captured_by=captured_by,
            page_snapshot_provider=page_snapshot_provider,
            page_snapshot_key=page_snapshot_key,
        )
        self.db.add(snap)
        self.db.flush()
        return snap
