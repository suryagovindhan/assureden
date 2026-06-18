"""
schemas/object_repository.py — Phase 1 Pydantic request/response schemas

Conventions:
  - *Create  → fields required at creation (no id, no timestamps)
  - *Update  → all fields Optional (PATCH semantics)
  - *Read    → full output shape including id + timestamps
  - Locator  → inline schema for the JSON array elements
  - *SearchResult → includes full path (application/module/page names)
  - PaginatedResponse[T] → generic wrapper used across all list endpoints
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────────
# Generic paginated wrapper
# ─────────────────────────────────────────────────────────────────────────────

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    offset: int
    limit: int


# ─────────────────────────────────────────────────────────────────────────────
# Locator element (JSON array item inside PageObject.locators)
# ─────────────────────────────────────────────────────────────────────────────

LocatorType = Literal["CSS_SELECTOR", "XPATH", "ID", "ARIA_LABEL", "TEST_ID", "TEXT"]
AddedBy     = Literal["MANUAL", "RECORDER"]


class Locator(BaseModel):
    """Single locator element. Stored as an item in PageObject.locators JSON array."""
    type:       LocatorType
    value:      str = Field(..., min_length=1, max_length=1000)
    priority:   int = Field(default=1, ge=1, le=99)
    is_primary: bool = False
    is_active:  bool = True
    added_by:   AddedBy = "MANUAL"
    added_at:   Optional[str] = None   # ISO 8601 string; set server-side on create
    notes:      Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# Application
# ─────────────────────────────────────────────────────────────────────────────

ObjectStatus = Literal["ACTIVE", "DEPRECATED", "ARCHIVED"]


class ApplicationCreate(BaseModel):
    name:        str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None
    status:      ObjectStatus = "ACTIVE"
    tags:        Optional[List[str]] = None
    owner_team:  Optional[str] = Field(default=None, max_length=100)


class ApplicationUpdate(BaseModel):
    name:        Optional[str] = Field(default=None, min_length=1, max_length=150)
    description: Optional[str] = None
    status:      Optional[ObjectStatus] = None
    tags:        Optional[List[str]] = None
    owner_team:  Optional[str] = Field(default=None, max_length=100)
    owner_user_id: Optional[uuid.UUID] = None


class ApplicationRead(BaseModel):
    id:           uuid.UUID
    org_id:       uuid.UUID
    name:         str
    description:  Optional[str]
    status:       str
    tags:         Optional[List[str]]
    owner_user_id: Optional[uuid.UUID]
    owner_team:   Optional[str]
    created_by:   Optional[uuid.UUID]
    created_at:   datetime
    updated_at:   datetime
    deleted_at:   Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# Module
# ─────────────────────────────────────────────────────────────────────────────

class ModuleCreate(BaseModel):
    name:           str = Field(..., min_length=1, max_length=150)
    description:    Optional[str] = None
    status:         ObjectStatus = "ACTIVE"
    tags:           Optional[List[str]] = None
    owner_team:     Optional[str] = Field(default=None, max_length=100)
    owner_user_id:  Optional[uuid.UUID] = None


class ModuleUpdate(BaseModel):
    name:           Optional[str] = Field(default=None, min_length=1, max_length=150)
    description:    Optional[str] = None
    status:         Optional[ObjectStatus] = None
    tags:           Optional[List[str]] = None
    owner_team:     Optional[str] = Field(default=None, max_length=100)
    owner_user_id:  Optional[uuid.UUID] = None


class ModuleRead(BaseModel):
    id:             uuid.UUID
    org_id:         uuid.UUID
    application_id: uuid.UUID
    name:           str
    description:    Optional[str]
    status:         str
    tags:           Optional[List[str]]
    owner_user_id:  Optional[uuid.UUID]
    owner_team:     Optional[str]
    created_by:     Optional[uuid.UUID]
    created_at:     datetime
    updated_at:     datetime
    deleted_at:     Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────

class PageCreate(BaseModel):
    name:         str = Field(..., min_length=1, max_length=150)
    description:  Optional[str] = None
    url_pattern:  Optional[str] = Field(default=None, max_length=500)
    status:       ObjectStatus = "ACTIVE"
    tags:         Optional[List[str]] = None
    owner_team:   Optional[str] = Field(default=None, max_length=100)
    owner_user_id: Optional[uuid.UUID] = None


class PageUpdate(BaseModel):
    name:         Optional[str] = Field(default=None, min_length=1, max_length=150)
    description:  Optional[str] = None
    url_pattern:  Optional[str] = Field(default=None, max_length=500)
    status:       Optional[ObjectStatus] = None
    tags:         Optional[List[str]] = None
    owner_team:   Optional[str] = Field(default=None, max_length=100)
    owner_user_id: Optional[uuid.UUID] = None


class PageRead(BaseModel):
    id:           uuid.UUID
    org_id:       uuid.UUID
    module_id:    uuid.UUID
    name:         str
    description:  Optional[str]
    url_pattern:  Optional[str]
    status:       str
    tags:         Optional[List[str]]
    owner_user_id: Optional[uuid.UUID]
    owner_team:   Optional[str]
    created_by:   Optional[uuid.UUID]
    created_at:   datetime
    updated_at:   datetime
    deleted_at:   Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# PageObject
# ─────────────────────────────────────────────────────────────────────────────

ObjectType  = Literal[
    "INPUT", "BUTTON", "LINK", "DROPDOWN", "CHECKBOX", "RADIO",
    "TABLE", "CONTAINER", "TEXT", "IFRAME", "DATE_PICKER", "FILE_UPLOAD",
]
PageArea    = Literal["HEADER", "BODY", "FOOTER", "MODAL", "SIDEBAR", "NAVIGATION"]
Criticality = Literal["HIGH", "MEDIUM", "LOW"]
POStatus    = Literal["DRAFT", "ACTIVE", "DEPRECATED", "ARCHIVED"]


class PageObjectCreate(BaseModel):
    name:            str = Field(..., min_length=1, max_length=200)
    description:     Optional[str] = None
    object_type:     ObjectType
    page_area:       Optional[PageArea] = None
    criticality:     Criticality = "MEDIUM"
    status:          POStatus = "DRAFT"
    locators:        Optional[List[Locator]] = Field(default_factory=list)
    search_keywords: Optional[List[str]] = Field(default_factory=list)
    tags:            Optional[List[str]] = None
    owner_user_id:   Optional[uuid.UUID] = None
    owner_team:      Optional[str] = Field(default=None, max_length=100)


class PageObjectUpdate(BaseModel):
    name:            Optional[str] = Field(default=None, min_length=1, max_length=200)
    description:     Optional[str] = None
    object_type:     Optional[ObjectType] = None
    page_area:       Optional[PageArea] = None
    criticality:     Optional[Criticality] = None
    status:          Optional[POStatus] = None
    locators:        Optional[List[Locator]] = None
    search_keywords: Optional[List[str]] = None
    tags:            Optional[List[str]] = None
    owner_user_id:   Optional[uuid.UUID] = None
    owner_team:      Optional[str] = Field(default=None, max_length=100)
    last_validated_at: Optional[datetime] = None


class PageObjectRead(BaseModel):
    id:              uuid.UUID
    org_id:          uuid.UUID
    page_id:         uuid.UUID
    name:            str
    description:     Optional[str]
    object_type:     str
    page_area:       Optional[str]
    criticality:     str
    status:          str
    locators:        Optional[List[dict]]   # raw dicts from JSON column
    search_keywords: Optional[List[str]]
    tags:            Optional[List[str]]
    owner_user_id:   Optional[uuid.UUID]
    owner_team:      Optional[str]
    last_validated_at: Optional[datetime]
    last_validated_by: Optional[uuid.UUID]
    created_by:      Optional[uuid.UUID]
    created_at:      datetime
    updated_at:      datetime
    deleted_at:      Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PageObjectSearchResult(BaseModel):
    """
    Search result includes full hierarchy path — no N+1 from UI side.
    Computed in a single JOIN query in the repository.
    """
    id:               uuid.UUID
    name:             str
    object_type:      str
    page_area:        Optional[str]
    criticality:      str
    status:           str
    tags:             Optional[List[str]]
    application_id:   uuid.UUID
    application_name: str
    module_id:        uuid.UUID
    module_name:      str
    page_id:          uuid.UUID
    page_name:        str


class PageObjectSearchResponse(BaseModel):
    items:  List[PageObjectSearchResult]
    total:  int
    offset: int
    limit:  int
    query:  str


# ─────────────────────────────────────────────────────────────────────────────
# PageObjectSnapshot
# ─────────────────────────────────────────────────────────────────────────────

class PageObjectSnapshotCreate(BaseModel):
    storage_provider:       str = Field(default="local", max_length=30)
    object_key:             str = Field(..., min_length=1, max_length=1000)
    snapshot_metadata:      Optional[dict] = None
    bounding_box:           Optional[dict] = None
    capture_url:            Optional[str] = Field(default=None, max_length=500)
    page_snapshot_provider: Optional[str] = Field(default=None, max_length=30)
    page_snapshot_key:      Optional[str] = Field(default=None, max_length=1000)


class PageObjectSnapshotRead(BaseModel):
    id:                     uuid.UUID
    org_id:                 uuid.UUID
    page_object_id:         uuid.UUID
    storage_provider:       str
    object_key:             str
    snapshot_metadata:      Optional[dict]
    bounding_box:           Optional[dict]
    capture_url:            Optional[str]
    captured_by:            Optional[uuid.UUID]
    page_snapshot_provider: Optional[str]
    page_snapshot_key:      Optional[str]
    created_at:             datetime

    model_config = ConfigDict(from_attributes=True)
