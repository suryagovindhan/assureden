"""
api/artifacts/router.py — Phase 5: Artifact upload, listing, and serving.

Endpoints:
  POST /runs/{run_id}/artifacts
      Upload a new artifact for a run. Accepted from agents (API key auth)
      AND from authenticated users (Bearer token auth). The upload endpoint
      accepts multipart/form-data so agents can stream large files.

  GET  /runs/{run_id}/artifacts
      List all artifacts for a run. Operator-facing; requires Bearer auth.

  GET  /artifacts/{artifact_id}
      Redirect (or serve) an artifact. Returns a presigned URL for cloud
      backends, or serves bytes directly for local storage.

Storage key format: <org_id>/<run_id>/<artifact_type>/<filename>
"""

from __future__ import annotations

import mimetypes
import uuid
from typing import Optional
from uuid import UUID
from pathlib import PurePosixPath
from sqlalchemy import select

from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, Form, status,
)
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import CurrentUser, require_role
from app.api.executions.router import get_agent_from_api_key
from app.models.executions import TestRun, StepResult
from app.db.base import utcnow
from app.db.session import get_db
from app.db.repositories.executions import TestRunRepository
from app.models.artifacts import RunArtifact, ARTIFACT_TYPES
from app.storage import get_storage

router = APIRouter(tags=["artifacts"])


# ── Upload ────────────────────────────────────────────────────────────────────

MAX_ARTIFACT_BYTES = 100 * 1024 * 1024  # 100 MB hard limit


@router.post("/runs/{run_id}/artifacts", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_role("TESTER"))])
async def upload_artifact(
    run_id: UUID,
    file: UploadFile = File(...),
    artifact_type: str = Form(..., description="SCREENSHOT | VIDEO | LOG | HAR | TRACE"),
    step_result_id: Optional[str] = Form(None),
    # Auth: Bearer token (operator/user) takes precedence; agent API key is fallback
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """
    Upload an artifact for a run.

    Accepts multipart/form-data with:
      file             — the artifact binary
      artifact_type    — SCREENSHOT | VIDEO | LOG | HAR | TRACE
      step_result_id   — optional; links artifact to a specific step

    Auth: Bearer token (operator) is required.
    Agents should use a dedicated agent-upload endpoint (Phase 5.5+).
    """
    org_id = current_user.org_id

    # ── Validate artifact_type ────────────────────────────────────────────────
    if artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid artifact_type. Must be one of: {ARTIFACT_TYPES}",
        )

    # ── Validate run belongs to org ──────────────────────────────────────────
    run_repo = TestRunRepository(db)
    run = run_repo.get_run(run_id, org_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # ── Read upload (with size guard) ─────────────────────────────────────────
    data = await file.read(MAX_ARTIFACT_BYTES + 1)
    if len(data) > MAX_ARTIFACT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Artifact exceeds {MAX_ARTIFACT_BYTES // (1024*1024)} MB limit",
        )

    filename = PurePosixPath((file.filename or "artifact").replace("\\", "/")).name
    filename = "".join(c for c in filename if c.isascii() and (c.isalnum() or c in "._-"))[:200] or "artifact"
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    # ── Storage key: <org_id>/<run_id>/<type>/<filename> ─────────────────────
    storage_key = f"{org_id}/{run_id}/{artifact_type.lower()}/{uuid.uuid4().hex}/{filename}"

    try:
        step_result_uuid = UUID(step_result_id) if step_result_id else None
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid step result ID")
    if step_result_uuid and not db.scalar(select(StepResult.id).where(
        StepResult.id == step_result_uuid, StepResult.run_id == run_id, StepResult.org_id == org_id,
    )):
        raise HTTPException(status_code=422, detail="Step result does not belong to this run")

    storage = get_storage()
    storage.save(storage_key, data, content_type)

    # ── Persist metadata ──────────────────────────────────────────────────────

    artifact = RunArtifact(
        org_id=org_id,
        run_id=run_id,
        step_result_id=step_result_uuid,
        artifact_type=artifact_type,
        storage_key=storage_key,
        filename=filename,
        size_bytes=len(data),
        content_type=content_type,
    )
    db.add(artifact)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(storage_key)
        raise
    db.refresh(artifact)

    return _artifact_out(artifact)


@router.post("/runs/{run_id}/agent-artifacts", status_code=201)
async def upload_agent_artifact(
    run_id: UUID, lease_id: UUID = Form(...), execution_step_id: UUID = Form(...),
    file: UploadFile = File(...), db: Session = Depends(get_db),
    agent=Depends(get_agent_from_api_key),
):
    run = db.scalar(select(TestRun).where(
        TestRun.id == run_id, TestRun.org_id == agent.org_id,
    ).with_for_update())
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if (run.agent_id != agent.id or run.lease_id != lease_id
            or run.status not in {"DISPATCHED", "RUNNING"}
            or not run.lease_expires_at or run.lease_expires_at <= utcnow()):
        raise HTTPException(status_code=409, detail="Run lease is not active")
    if run.deadline_at is not None and run.deadline_at <= utcnow():
        raise HTTPException(status_code=409, detail="Execution deadline has expired")
    result_id = db.scalar(select(StepResult.id).where(
        StepResult.run_id == run_id, StepResult.execution_step_id == execution_step_id,
    ))
    if result_id is None:
        raise HTTPException(status_code=422, detail="Submit the step result before its evidence")
    # The modern agent currently uploads PNG screenshots only.
    if file.content_type != "image/png" or await file.read(8) != b"\x89PNG\r\n\x1a\n":
        raise HTTPException(status_code=422, detail="Expected a PNG screenshot")
    await file.seek(0)
    return await upload_artifact(run_id, file, "SCREENSHOT", str(result_id), agent, db)


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/runs/{run_id}/artifacts")
def list_artifacts(
    run_id: UUID,
    artifact_type: Optional[str] = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """List all artifacts for a run, optionally filtered by artifact_type."""
    run_repo = TestRunRepository(db)
    run = run_repo.get_run(run_id, current_user.org_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    q = db.query(RunArtifact).filter(
        RunArtifact.run_id == run_id,
        RunArtifact.org_id == current_user.org_id,
    )
    if artifact_type:
        q = q.filter(RunArtifact.artifact_type == artifact_type)

    artifacts = q.order_by(RunArtifact.created_at.asc()).all()
    return {"total": len(artifacts), "items": [_artifact_out(a) for a in artifacts]}


# ── Serve / Redirect ──────────────────────────────────────────────────────────

@router.get("/artifacts/{artifact_id}")
def get_artifact(
    artifact_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """
    Serve or redirect to an artifact.

    For local storage: serves the bytes directly with correct Content-Type.
    For cloud storage: returns a 302 redirect to a presigned URL.
    """
    artifact = db.query(RunArtifact).filter(
        RunArtifact.id == artifact_id,
        RunArtifact.org_id == current_user.org_id,
    ).first()
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    storage = get_storage()

    if settings.ARTIFACT_STORAGE_PROVIDER == "local":
        try:
            data = storage.read(artifact.storage_key)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Artifact file missing from storage")
        disposition = "inline" if artifact.content_type in {"image/png", "image/jpeg"} else "attachment"
        return Response(
            content=data,
            media_type=artifact.content_type,
            headers={
                "Content-Disposition": f'{disposition}; filename="{artifact.filename}"',
                "X-Content-Type-Options": "nosniff",
                "Content-Length": str(artifact.size_bytes),
            },
        )

    # Cloud backends: presign and redirect
    presigned = storage.presign(artifact.storage_key, expires_seconds=3600)
    return RedirectResponse(url=presigned, status_code=302)


# ── Serialiser ────────────────────────────────────────────────────────────────

def _artifact_out(a: RunArtifact) -> dict:
    return {
        "id":              str(a.id),
        "run_id":          str(a.run_id),
        "step_result_id":  str(a.step_result_id) if a.step_result_id else None,
        "artifact_type":   a.artifact_type,
        "filename":        a.filename,
        "size_bytes":      a.size_bytes,
        "content_type":    a.content_type,
        "url":             f"/api/artifacts/{a.id}",
        "created_at":      a.created_at.isoformat() if a.created_at else None,
    }
