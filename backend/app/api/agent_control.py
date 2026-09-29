"""Product-driven pairing and recording. The desktop initiates all connections."""
import io
import secrets
import zipfile
from datetime import timedelta, datetime
from pathlib import Path
from uuid import UUID
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.dependencies import CurrentUser, require_role
from app.db.base import utcnow
from app.db.session import get_db
from app.db.repositories.foundation import AgentRepository, AuditEventRepository
from app.models.foundation import Agent
from app.models.agent_control import AgentEnrollment, BrowserRecording
from app.models.executions import TestRun
from app.models.drafts import DraftAsset
from app.api.agents.router import get_agent_from_api_key
from app.schemas.drafts import Recording
from app.api.drafts import content

router = APIRouter(prefix="/agent-control", tags=["Agent setup and recording"])
ACTIVE = ["REQUESTED", "RECORDING", "STOP_REQUESTED"]


class EnrollmentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ClaimRequest(BaseModel):
    code: str = Field(min_length=20, max_length=100)
    key_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.post("/enroll", dependencies=[Depends(require_role("ADMIN"))])
def enroll(body: EnrollmentRequest, current_user: CurrentUser, db: Session = Depends(get_db)):
    code = secrets.token_urlsafe(24)
    _, unused = AgentRepository.generate_api_key()
    agent = AgentRepository(db).create_agent(current_user.org_id, body.name, unused)
    db.add(AgentEnrollment(agent_id=agent.id, code_hash=AgentRepository.hash_api_key(code),
                           expires_at=utcnow() + timedelta(minutes=10)))
    AuditEventRepository(db).write(current_user.org_id, "Agent", agent.id, "CREATED", actor_id=current_user.id)
    db.commit()
    return {"agent_id": str(agent.id), "code": code, "expires_in_seconds": 600}


@router.post("/claim")
def claim(body: ClaimRequest, db: Session = Depends(get_db)):
    row = db.scalar(select(AgentEnrollment).where(
        AgentEnrollment.code_hash == AgentRepository.hash_api_key(body.code)).with_for_update())
    if row is None or row.expires_at < utcnow():
        raise HTTPException(401, "Pairing code is invalid or expired. Generate a new code in AssureDen.")
    agent = db.get(Agent, row.agent_id)
    if agent is None or agent.deleted_at:
        raise HTTPException(401, "Agent was removed")
    if row.claimed_at and agent.api_key_hash != body.key_hash:
        raise HTTPException(409, "Pairing code has already been used")
    agent.api_key_hash = body.key_hash
    row.claimed_at = row.claimed_at or utcnow()
    db.commit()
    return {"agent_id": str(agent.id), "name": agent.name}


@router.get("/download", dependencies=[Depends(require_role("ADMIN"))])
def download():
    root = Path(__file__).resolve().parents[3] / "execution_agent"
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("__init__.py", "worker.py", "recorder.py", "desktop.py", "requirements.txt"):
            archive.write(root / name, "execution_agent/" + name)
        archive.write(root / "Install.cmd", "Install.cmd")
        archive.write(root / "Install.ps1", "Install.ps1")
    data.seek(0)
    return StreamingResponse(data, media_type="application/zip",
                             headers={"Content-Disposition": 'attachment; filename="AssureDen-Agent.zip"'})


class StartRecording(BaseModel):
    agent_id: UUID
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def valid_url(self):
        url = urlparse(self.url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError("Use an HTTP or HTTPS URL without embedded credentials")
        return self


def output(row):
    expired = row.status in ACTIVE and row.expires_at <= utcnow()
    return {"id": str(row.id), "name": row.name, "url": row.url, "agent_id": str(row.agent_id),
            "status": "EXPIRED" if expired else row.status,
            "draft_id": str(row.draft_id) if row.draft_id else None,
            "error": "Recording expired. Start a new recording." if expired else row.error}


@router.get("/recordings")
def recordings(current_user: CurrentUser, db: Session = Depends(get_db)):
    return [output(r) for r in db.scalars(select(BrowserRecording).where(
        BrowserRecording.org_id == current_user.org_id).order_by(BrowserRecording.created_at.desc()).limit(50)).all()]


@router.post("/recordings", status_code=201, dependencies=[Depends(require_role("TESTER"))])
def start_recording(body: StartRecording, current_user: CurrentUser, db: Session = Depends(get_db)):
    agent = db.scalar(select(Agent).where(Agent.id == body.agent_id,
        Agent.org_id == current_user.org_id, Agent.deleted_at.is_(None)).with_for_update())
    if agent is None:
        raise HTTPException(404, "Agent not found")
    if not agent.last_heartbeat or agent.last_heartbeat < utcnow() - timedelta(seconds=30):
        raise HTTPException(409, "Agent is disconnected. Open AssureDen Agent on that computer.")
    if not (agent.capabilities or {}).get("recording"):
        raise HTTPException(409, "Install the current desktop agent to record")
    busy = db.scalar(select(TestRun.id).where(TestRun.agent_id == agent.id,
        TestRun.status.in_(["DISPATCHED", "RUNNING"])).limit(1))
    recording = db.scalar(select(BrowserRecording.id).where(BrowserRecording.agent_id == agent.id,
        BrowserRecording.status.in_(ACTIVE), BrowserRecording.expires_at > utcnow()).limit(1))
    if busy or recording:
        raise HTTPException(409, "Agent is busy. Finish its current run or recording first.")
    row = BrowserRecording(org_id=current_user.org_id, created_by=current_user.id,
        agent_id=agent.id, name=body.name, url=body.url, expires_at=utcnow() + timedelta(minutes=30))
    db.add(row); db.flush()
    AuditEventRepository(db).write(current_user.org_id, "BrowserRecording", row.id, "CREATED", actor_id=current_user.id)
    db.commit()
    return output(row)


@router.post("/recordings/{recording_id}/stop", dependencies=[Depends(require_role("TESTER"))])
def stop(recording_id: UUID, current_user: CurrentUser, db: Session = Depends(get_db)):
    row = db.scalar(select(BrowserRecording).where(BrowserRecording.id == recording_id,
        BrowserRecording.org_id == current_user.org_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Recording not found")
    if row.status == "REQUESTED":
        row.status = "CANCELLED"
    elif row.status == "RECORDING":
        row.status = "STOP_REQUESTED"
    db.commit()
    return output(row)


@router.post("/poll")
def poll(agent=Depends(get_agent_from_api_key), db: Session = Depends(get_db)):
    db.scalar(select(Agent.id).where(Agent.id == agent.id).with_for_update())
    row = db.scalar(select(BrowserRecording).where(BrowserRecording.agent_id == agent.id,
        BrowserRecording.org_id == agent.org_id, BrowserRecording.status == "REQUESTED",
        BrowserRecording.expires_at > utcnow()).order_by(BrowserRecording.created_at).with_for_update())
    if row is None:
        return None
    row.status = "RECORDING"
    db.commit()
    return output(row)


@router.post("/recordings/{recording_id}/cancel", dependencies=[Depends(require_role("TESTER"))])
def cancel_recording(recording_id: UUID, current_user: CurrentUser, db: Session = Depends(get_db)):
    row = db.scalar(select(BrowserRecording).where(BrowserRecording.id == recording_id,
        BrowserRecording.org_id == current_user.org_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Recording not found")
    if row.status in ACTIVE:
        row.status = "CANCELLED"
        AuditEventRepository(db).write(row.org_id, "BrowserRecording", row.id, "CANCELLED", actor_id=current_user.id)
    db.commit()
    return output(row)


def assigned(db, recording_id, agent):
    row = db.scalar(select(BrowserRecording).where(BrowserRecording.id == recording_id,
        BrowserRecording.agent_id == agent.id, BrowserRecording.org_id == agent.org_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Recording not found")
    return row


@router.get("/recordings/{recording_id}/state")
def state(recording_id: UUID, agent=Depends(get_agent_from_api_key), db: Session = Depends(get_db)):
    return output(assigned(db, recording_id, agent))


@router.post("/recordings/{recording_id}/complete")
def complete(recording_id: UUID, body: Recording, agent=Depends(get_agent_from_api_key), db: Session = Depends(get_db)):
    row = assigned(db, recording_id, agent)
    if row.status == "COMPLETED":
        return output(row)
    if row.status not in ["RECORDING", "STOP_REQUESTED"] or row.expires_at <= utcnow():
        raise HTTPException(409, "Recording is no longer active")
    data = content(body)
    data["name"] = row.name
    draft = DraftAsset(org_id=row.org_id, name=row.name, recording=data, created_by=row.created_by)
    db.add(draft); db.flush()
    row.draft_id = draft.id; row.status = "COMPLETED"
    AuditEventRepository(db).write(row.org_id, "DraftAsset", draft.id, "CREATED", actor_id=row.created_by)
    db.commit()
    return output(row)


@router.post("/recordings/{recording_id}/failed")
def failed(recording_id: UUID, agent=Depends(get_agent_from_api_key), db: Session = Depends(get_db)):
    row = assigned(db, recording_id, agent)
    if row.status in ACTIVE:
        row.status = "FAILED"; row.error = "Browser recording failed. Check the agent connection and target URL, then retry."
    db.commit()
    return output(row)
