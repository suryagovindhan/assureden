"""
models/object_repository.py — Phase 1 Object Repository ORM models

Hierarchy:
  Application → Module → Page → PageObject → PageObjectSnapshot

Invariants (enforced by OrgScopedRepository):
  - Every entity carries org_id + deleted_at (except PageObjectSnapshot, append-only)
  - Unique constraints prevent name collisions within the same parent
  - Soft delete cascades via query visibility, not DB CASCADE
  - PageObjectSnapshot uses storage abstraction (storage_provider + object_key + metadata)

Locator JSON shape (per element in PageObject.locators JSON array):
  {
    "type":       "CSS_SELECTOR | XPATH | ID | ARIA_LABEL | TEST_ID | TEXT",
    "value":      "#username",
    "priority":   1,            ← 1=highest; lower number dispatched first
    "is_primary": true,
    "is_active":  true,         ← disable without deleting history
    "added_by":   "MANUAL | RECORDER",
    "added_at":   "2026-06-05T10:00:00Z",
    "notes":      null          ← e.g. "Fallback after page redesign"
  }

object_type enum (v1):
  INPUT | BUTTON | LINK | DROPDOWN | CHECKBOX | RADIO
  TABLE | CONTAINER | TEXT | IFRAME | DATE_PICKER | FILE_UPLOAD
  (TREE, GRID, TAB, ACCORDION, RICH_TEXT → CONTAINER in v1)
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ─────────────────────────────────────────────────────────────────────────────
# Application
# ─────────────────────────────────────────────────────────────────────────────

class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        # Multi-tenant indexes
        Index("idx_applications_org_id",      "org_id"),
        Index("idx_applications_org_deleted",  "org_id", "deleted_at"),
        Index("idx_applications_org_status",   "org_id", "status"),
        # Prevent duplicate app names within the same org
        UniqueConstraint("org_id", "name", name="uq_applications_org_name"),
    )

    id:          Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:      Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), nullable=False)
    name:        Mapped[str]              = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]]    = mapped_column(Text, nullable=True)
    status:      Mapped[str]              = mapped_column(String(20), nullable=False, default="ACTIVE")
    # ACTIVE | DEPRECATED | ARCHIVED
    tags:        Mapped[Optional[list]]   = mapped_column(JSON, nullable=True)
    # ["web", "vault", "pam"]

    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", use_alter=True, name="fk_application_owner"),
        nullable=True,
    )
    owner_team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Soft delete
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    modules: Mapped[list["Module"]] = relationship("Module", back_populates="application")


# ─────────────────────────────────────────────────────────────────────────────
# Module
# ─────────────────────────────────────────────────────────────────────────────

class Module(Base):
    __tablename__ = "modules"
    __table_args__ = (
        Index("idx_modules_org_id",         "org_id"),
        Index("idx_modules_org_deleted",     "org_id", "deleted_at"),
        Index("idx_modules_application",     "application_id"),
        Index("idx_modules_org_app_deleted", "org_id", "application_id", "deleted_at"),
        # Prevent duplicate module names within the same application
        UniqueConstraint("org_id", "application_id", "name", name="uq_modules_org_app_name"),
    )

    id:             Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:         Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), nullable=False)
    application_id: Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False)
    name:           Mapped[str]              = mapped_column(String(150), nullable=False)
    description:    Mapped[Optional[str]]    = mapped_column(Text, nullable=True)
    status:         Mapped[str]              = mapped_column(String(20), nullable=False, default="ACTIVE")
    tags:           Mapped[Optional[list]]   = mapped_column(JSON, nullable=True)

    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", use_alter=True, name="fk_module_owner"),
        nullable=True,
    )
    owner_team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Soft delete
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    application: Mapped["Application"] = relationship("Application", back_populates="modules")
    pages:       Mapped[list["Page"]]  = relationship("Page", back_populates="module")


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────

class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (
        Index("idx_pages_org_id",          "org_id"),
        Index("idx_pages_org_deleted",     "org_id", "deleted_at"),
        Index("idx_pages_module",          "module_id"),
        Index("idx_pages_org_mod_deleted", "org_id", "module_id", "deleted_at"),
        # Prevent duplicate page names within the same module
        UniqueConstraint("org_id", "module_id", "name", name="uq_pages_org_module_name"),
    )

    id:          Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:      Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), nullable=False)
    module_id:   Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), ForeignKey("modules.id"), nullable=False)
    name:        Mapped[str]              = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]]    = mapped_column(Text, nullable=True)
    url_pattern: Mapped[Optional[str]]    = mapped_column(String(500), nullable=True)
    # e.g. "/accounts/*/details" — used by recorder for auto-matching
    status:      Mapped[str]              = mapped_column(String(20), nullable=False, default="ACTIVE")
    tags:        Mapped[Optional[list]]   = mapped_column(JSON, nullable=True)

    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", use_alter=True, name="fk_page_owner"),
        nullable=True,
    )
    owner_team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Soft delete
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    module:       Mapped["Module"]            = relationship("Module", back_populates="pages")
    page_objects: Mapped[list["PageObject"]]  = relationship("PageObject", back_populates="page")


# ─────────────────────────────────────────────────────────────────────────────
# PageObject
# ─────────────────────────────────────────────────────────────────────────────

class PageObject(Base):
    __tablename__ = "page_objects"
    __table_args__ = (
        Index("idx_page_objects_org_id",      "org_id"),
        Index("idx_page_objects_org_deleted",  "org_id", "deleted_at"),
        Index("idx_page_objects_page",         "page_id"),
        Index("idx_page_objects_status",       "org_id", "status"),
        Index("idx_page_objects_criticality",  "org_id", "criticality"),
        # Prevent duplicate object names within the same page
        UniqueConstraint("org_id", "page_id", "name", name="uq_page_objects_org_page_name"),
    )

    id:          Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:      Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), nullable=False)
    page_id:     Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), ForeignKey("pages.id"), nullable=False)

    name:        Mapped[str]              = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]]    = mapped_column(Text, nullable=True)

    # ── Classification ────────────────────────────────────────────
    object_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # INPUT | BUTTON | LINK | DROPDOWN | CHECKBOX | RADIO
    # TABLE | CONTAINER | TEXT | IFRAME | DATE_PICKER | FILE_UPLOAD

    page_area: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # HEADER | BODY | FOOTER | MODAL | SIDEBAR | NAVIGATION

    criticality: Mapped[str] = mapped_column(String(10), nullable=False, default="MEDIUM")
    # HIGH | MEDIUM | LOW

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    # DRAFT | ACTIVE | DEPRECATED | ARCHIVED

    # ── Locators (v1: JSON array; v2: PageObjectLocator table) ────
    # Each element: { type, value, priority, is_primary, is_active,
    #                 added_by, added_at, notes }
    locators: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)

    # ── Keyword Search ────────────────────────────────────────────
    # JSON array of strings; v2 activates GIN index + ARRAY(Text)
    search_keywords: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    # e.g. ["Login Button", "Sign In", "Authenticate"]

    # ── Ownership & Governance ────────────────────────────────────
    tags:        Mapped[Optional[list]]       = mapped_column(JSON, nullable=True)
    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", use_alter=True, name="fk_page_object_owner"),
        nullable=True,
    )
    owner_team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    last_validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_validated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", use_alter=True, name="fk_page_object_validator"),
        nullable=True,
    )

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Soft delete
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    page:      Mapped["Page"]                        = relationship("Page", back_populates="page_objects")
    snapshots: Mapped[list["PageObjectSnapshot"]]    = relationship("PageObjectSnapshot", back_populates="page_object")


# ─────────────────────────────────────────────────────────────────────────────
# PageObjectSnapshot  (append-only — no deleted_at)
# ─────────────────────────────────────────────────────────────────────────────

class PageObjectSnapshot(Base):
    """
    Immutable, append-only visual record of a PageObject at a point in time.

    Storage abstraction matches ExecutionArtifact pattern:
      storage_provider: "local" | "s3" | "azure_blob" | "nas"
      object_key:       provider-relative path/key
      metadata:         { bucket, region, content_type, size_bytes, ... }

    Never physically deleted — history is permanent.
    """
    __tablename__ = "page_object_snapshots"
    __table_args__ = (
        Index("idx_po_snapshots_page_object", "page_object_id"),
        Index("idx_po_snapshots_org",         "org_id"),
    )

    id:             Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:         Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), nullable=False)
    page_object_id: Mapped[uuid.UUID]     = mapped_column(UUID(as_uuid=True), ForeignKey("page_objects.id"), nullable=False)

    # ── Screenshot storage (abstracted) ───────────────────────────
    storage_provider: Mapped[str]              = mapped_column(String(30), nullable=False, default="local")
    # "local" | "s3" | "azure_blob" | "nas"
    object_key:       Mapped[str]              = mapped_column(String(1000), nullable=False)
    # local:      "snapshots/uuid/screenshot.png"
    # s3:         "page-objects/uuid/snapshot.png"
    # azure_blob: "container/page-objects/uuid/snapshot.png"
    snapshot_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    # { "content_type": "image/png", "size_bytes": 45231,
    #   "bucket": "stest-artifacts", "region": "ap-south-1",
    #   "presigned_url_expires_at": "2026-06-05T19:00:00Z" }

    # ── Page-level snapshot (optional DOM/HTML capture) ───────────
    page_snapshot_provider: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    page_snapshot_key:      Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # ── Visual metadata ────────────────────────────────────────────
    bounding_box: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # { "x": 100, "y": 200, "width": 80, "height": 32 }

    captured_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", use_alter=True, name="fk_snapshot_captured_by"),
        nullable=True,
    )
    capture_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # URL the page was at when snapshot was taken

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    # Relationships
    page_object: Mapped["PageObject"] = relationship("PageObject", back_populates="snapshots")
