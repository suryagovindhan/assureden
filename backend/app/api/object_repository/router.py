"""
api/object_repository/router.py — Phase 1 Object Repository REST API

URL conventions:
  /api/applications                     — Application CRUD
  /api/applications/{app_id}/modules    — Module list/create under an app
  /api/modules/{module_id}              — Module CRUD
  /api/modules/{module_id}/pages        — Page list/create under a module
  /api/pages/{page_id}                  — Page CRUD
  /api/pages/{page_id}/objects          — PageObject list/create under a page
  /api/objects/{po_id}                  — PageObject CRUD + locator update
  /api/objects/search                   — Org-wide keyword search with path info
  /api/objects/{po_id}/snapshots        — PageObjectSnapshot list/create

Security:
  All endpoints require a valid JWT (current_user from auth middleware).
  org_id is always taken from current_user — never from request body or path.

Soft delete:
  DELETE endpoints set deleted_at + deleted_by. Never issue SQL DELETE.
  Children are hidden automatically via cascade join checks in repositories.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.db.repositories.object_repository import (
    ApplicationRepository,
    ModuleRepository,
    PageRepository,
    PageObjectRepository,
    PageObjectSnapshotRepository,
)
from app.models.foundation import User
from app.schemas.object_repository import (
    ApplicationCreate, ApplicationUpdate, ApplicationRead,
    ModuleCreate, ModuleUpdate, ModuleRead,
    PageCreate, PageUpdate, PageRead,
    PageObjectCreate, PageObjectUpdate, PageObjectRead,
    PageObjectSearchResult, PageObjectSearchResponse,
    PageObjectSnapshotCreate, PageObjectSnapshotRead,
    PaginatedResponse,
)

router = APIRouter(prefix="/object-repository", tags=["Object Repository"])


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────────────────────────────────────
# Applications
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/applications", response_model=PaginatedResponse[ApplicationRead])
def list_applications(
    offset: int = Query(default=0, ge=0),
    limit:  int = Query(default=50, ge=1, le=200),
    status: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = ApplicationRepository(db)
    filters = {}
    if status:
        filters["status"] = status
    items = repo.list(org_id=current_user.org_id, offset=offset, limit=limit, **filters)
    total = repo.count(org_id=current_user.org_id, **filters)
    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)


@router.post("/applications", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def create_application(
    body: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = ApplicationRepository(db)
    if repo.get_by_name(body.name, current_user.org_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Application named '{body.name}' already exists in this organisation.",
        )
    app = repo.create(
        org_id=current_user.org_id,
        name=body.name,
        description=body.description,
        status=body.status,
        tags=body.tags,
        owner_team=body.owner_team,
        created_by=current_user.id,
    )
    db.commit()
    db.refresh(app)
    return app


@router.get("/applications/{app_id}", response_model=ApplicationRead)
def get_application(
    app_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = ApplicationRepository(db)
    app = repo.get(app_id, current_user.org_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    return app


@router.put("/applications/{app_id}", response_model=ApplicationRead)
def update_application(
    app_id: UUID,
    body: ApplicationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = ApplicationRepository(db)
    app = repo.get(app_id, current_user.org_id)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    update_data = body.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != app.name:
        existing = repo.get_by_name(update_data["name"], current_user.org_id)
        if existing and existing.id != app_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Application named '{update_data['name']}' already exists.",
            )

    for field, value in update_data.items():
        setattr(app, field, value)
    db.commit()
    db.refresh(app)
    return app


@router.delete("/applications/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(
    app_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_lead(current_user)
    repo = ApplicationRepository(db)
    result = repo.soft_delete(app_id, current_user.org_id, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Application not found.")
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Modules
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/applications/{app_id}/modules", response_model=PaginatedResponse[ModuleRead])
def list_modules(
    app_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit:  int = Query(default=100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify the application is accessible
    app_repo = ApplicationRepository(db)
    if not app_repo.get(app_id, current_user.org_id):
        raise HTTPException(status_code=404, detail="Application not found.")

    repo = ModuleRepository(db)
    items = repo.list_by_application(app_id, current_user.org_id, offset=offset, limit=limit)
    total = repo.count_by_application(app_id, current_user.org_id)
    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)


@router.post("/applications/{app_id}/modules", response_model=ModuleRead, status_code=201)
def create_module(
    app_id: UUID,
    body: ModuleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app_repo = ApplicationRepository(db)
    if not app_repo.get(app_id, current_user.org_id):
        raise HTTPException(status_code=404, detail="Application not found.")

    repo = ModuleRepository(db)
    mod = repo.create(
        org_id=current_user.org_id,
        application_id=app_id,
        name=body.name,
        description=body.description,
        status=body.status,
        tags=body.tags,
        owner_team=body.owner_team,
        owner_user_id=body.owner_user_id,
        created_by=current_user.id,
    )
    db.commit()
    db.refresh(mod)
    return mod


@router.get("/modules/{module_id}", response_model=ModuleRead)
def get_module(
    module_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = ModuleRepository(db)
    mod = repo.get_with_app_check(module_id, current_user.org_id)
    if not mod:
        raise HTTPException(status_code=404, detail="Module not found.")
    return mod


@router.put("/modules/{module_id}", response_model=ModuleRead)
def update_module(
    module_id: UUID,
    body: ModuleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = ModuleRepository(db)
    mod = repo.get_with_app_check(module_id, current_user.org_id)
    if not mod:
        raise HTTPException(status_code=404, detail="Module not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(mod, field, value)
    db.commit()
    db.refresh(mod)
    return mod


@router.delete("/modules/{module_id}", status_code=204)
def delete_module(
    module_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_lead(current_user)
    repo = ModuleRepository(db)
    result = repo.soft_delete(module_id, current_user.org_id, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Module not found.")
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Pages
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/modules/{module_id}/pages", response_model=PaginatedResponse[PageRead])
def list_pages(
    module_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit:  int = Query(default=100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mod_repo = ModuleRepository(db)
    if not mod_repo.get_with_app_check(module_id, current_user.org_id):
        raise HTTPException(status_code=404, detail="Module not found.")

    repo = PageRepository(db)
    items = repo.list_by_module(module_id, current_user.org_id, offset=offset, limit=limit)
    total = repo.count_by_module(module_id, current_user.org_id)
    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)


@router.post("/modules/{module_id}/pages", response_model=PageRead, status_code=201)
def create_page(
    module_id: UUID,
    body: PageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mod_repo = ModuleRepository(db)
    if not mod_repo.get_with_app_check(module_id, current_user.org_id):
        raise HTTPException(status_code=404, detail="Module not found.")

    repo = PageRepository(db)
    page = repo.create(
        org_id=current_user.org_id,
        module_id=module_id,
        name=body.name,
        description=body.description,
        url_pattern=body.url_pattern,
        status=body.status,
        tags=body.tags,
        owner_team=body.owner_team,
        owner_user_id=body.owner_user_id,
        created_by=current_user.id,
    )
    db.commit()
    db.refresh(page)
    return page


@router.get("/pages/{page_id}", response_model=PageRead)
def get_page(
    page_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PageRepository(db)
    page = repo.get_with_hierarchy_check(page_id, current_user.org_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found.")
    return page


@router.put("/pages/{page_id}", response_model=PageRead)
def update_page(
    page_id: UUID,
    body: PageUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PageRepository(db)
    page = repo.get_with_hierarchy_check(page_id, current_user.org_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(page, field, value)
    db.commit()
    db.refresh(page)
    return page


@router.delete("/pages/{page_id}", status_code=204)
def delete_page(
    page_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_lead(current_user)
    repo = PageRepository(db)
    result = repo.soft_delete(page_id, current_user.org_id, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Page not found.")
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# PageObjects
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/objects/search", response_model=PageObjectSearchResponse)
def search_objects(
    q:      str = Query(..., min_length=1, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit:  int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Org-wide keyword search across PageObject.name and search_keywords.
    Returns full path context (application, module, page names) in one query.
    Route declared BEFORE /objects/{po_id} to avoid 'search' being treated as UUID.
    """
    repo = PageObjectRepository(db)
    raw = repo.search_by_keyword(q, current_user.org_id, offset=offset, limit=limit)
    total = repo.count_search(q, current_user.org_id)
    items = [PageObjectSearchResult(**{**r, "id": UUID(r["id"]),
                                       "application_id": UUID(r["application_id"]),
                                       "module_id": UUID(r["module_id"]),
                                       "page_id": UUID(r["page_id"])})
             for r in raw]
    return PageObjectSearchResponse(items=items, total=total, offset=offset, limit=limit, query=q)


@router.get("/pages/{page_id}/objects", response_model=PaginatedResponse[PageObjectRead])
def list_page_objects(
    page_id: UUID,
    offset:  int = Query(default=0, ge=0),
    limit:   int = Query(default=100, ge=1, le=200),
    status:  Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    page_repo = PageRepository(db)
    if not page_repo.get_with_hierarchy_check(page_id, current_user.org_id):
        raise HTTPException(status_code=404, detail="Page not found.")

    repo = PageObjectRepository(db)
    items = repo.list_by_page(page_id, current_user.org_id, offset=offset, limit=limit, status=status)
    total = repo.count(org_id=current_user.org_id, page_id=page_id)
    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)


@router.post("/pages/{page_id}/objects", response_model=PageObjectRead, status_code=201)
def create_page_object(
    page_id: UUID,
    body: PageObjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    page_repo = PageRepository(db)
    if not page_repo.get_with_hierarchy_check(page_id, current_user.org_id):
        raise HTTPException(status_code=404, detail="Page not found.")

    # Serialise locators to plain dicts (JSON-safe) + inject added_at
    locators_data = None
    if body.locators:
        now_str = _now().isoformat() + "Z"
        locators_data = [
            {**loc.model_dump(), "added_at": loc.added_at or now_str}
            for loc in body.locators
        ]

    repo = PageObjectRepository(db)
    po = repo.create(
        org_id=current_user.org_id,
        page_id=page_id,
        name=body.name,
        description=body.description,
        object_type=body.object_type,
        page_area=body.page_area,
        criticality=body.criticality,
        status=body.status,
        locators=locators_data or [],
        search_keywords=body.search_keywords or [],
        tags=body.tags,
        owner_user_id=body.owner_user_id,
        owner_team=body.owner_team,
        created_by=current_user.id,
    )
    db.commit()
    db.refresh(po)
    return po


@router.get("/objects/{po_id}", response_model=PageObjectRead)
def get_page_object(
    po_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PageObjectRepository(db)
    po = repo.get_with_hierarchy_check(po_id, current_user.org_id)
    if not po:
        raise HTTPException(status_code=404, detail="PageObject not found.")
    return po


@router.put("/objects/{po_id}", response_model=PageObjectRead)
def update_page_object(
    po_id: UUID,
    body: PageObjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PageObjectRepository(db)
    po = repo.get_with_hierarchy_check(po_id, current_user.org_id)
    if not po:
        raise HTTPException(status_code=404, detail="PageObject not found.")

    update_data = body.model_dump(exclude_unset=True)

    # Serialise locators if provided
    if "locators" in update_data and update_data["locators"] is not None:
        now_str = _now().isoformat() + "Z"
        update_data["locators"] = [
            {**loc.model_dump(), "added_at": loc.added_at or now_str}
            if hasattr(loc, "model_dump") else loc
            for loc in body.locators
        ]

    for field, value in update_data.items():
        setattr(po, field, value)
    db.commit()
    db.refresh(po)
    return po


@router.delete("/objects/{po_id}", status_code=204)
def delete_page_object(
    po_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_lead(current_user)
    repo = PageObjectRepository(db)
    result = repo.soft_delete(po_id, current_user.org_id, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="PageObject not found.")
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# PageObjectSnapshots  (append-only)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/objects/{po_id}/snapshots", response_model=PaginatedResponse[PageObjectSnapshotRead])
def list_snapshots(
    po_id:  UUID,
    offset: int = Query(default=0, ge=0),
    limit:  int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    po_repo = PageObjectRepository(db)
    if not po_repo.get_with_hierarchy_check(po_id, current_user.org_id):
        raise HTTPException(status_code=404, detail="PageObject not found.")

    snap_repo = PageObjectSnapshotRepository(db)
    items = snap_repo.list_by_page_object(po_id, current_user.org_id, offset=offset, limit=limit)
    return PaginatedResponse(items=items, total=len(items), offset=offset, limit=limit)


@router.post("/objects/{po_id}/snapshots", response_model=PageObjectSnapshotRead, status_code=201)
def create_snapshot(
    po_id: UUID,
    body:  PageObjectSnapshotCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    po_repo = PageObjectRepository(db)
    if not po_repo.get_with_hierarchy_check(po_id, current_user.org_id):
        raise HTTPException(status_code=404, detail="PageObject not found.")

    snap_repo = PageObjectSnapshotRepository(db)
    snap = snap_repo.create(
        org_id=current_user.org_id,
        page_object_id=po_id,
        storage_provider=body.storage_provider,
        object_key=body.object_key,
        snapshot_metadata=body.snapshot_metadata,
        bounding_box=body.bounding_box,
        capture_url=body.capture_url,
        captured_by=current_user.id,
        page_snapshot_provider=body.page_snapshot_provider,
        page_snapshot_key=body.page_snapshot_key,
    )
    db.commit()
    db.refresh(snap)
    return snap


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_ROLE_ORDER = {"VIEWER": 0, "TESTER": 1, "LEAD": 2, "ADMIN": 3}


def _require_lead(user: User) -> None:
    """Raise 403 if caller is below LEAD role."""
    if _ROLE_ORDER.get(user.role, 0) < _ROLE_ORDER["LEAD"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="LEAD or ADMIN role required for this action.",
        )
