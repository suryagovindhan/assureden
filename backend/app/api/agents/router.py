"""
api/agents/router.py — Agent registration, heartbeat, CRUD
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import CurrentUser, require_role
from app.db.base import utcnow
from app.db.session import get_db
from app.db.repositories.foundation import (
    AgentRepository, AgentSessionRepository, AuditEventRepository,
)

router = APIRouter(prefix="/agents", tags=["agents"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class AgentRegisterRequest(BaseModel):
    name: str
    hostname: Optional[str] = None
    os_version: Optional[str] = None
    agent_version: Optional[str] = None
    protocol_version: Optional[int] = None
    payload_versions_supported: Optional[list[int]] = None
    browser_versions: Optional[dict] = None
    installed_apps: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    capabilities: Optional[dict] = None
    host_info: Optional[dict] = None
    max_parallel_sessions: int = 1


class AgentRegisterResponse(BaseModel):
    id: UUID
    name: str
    api_key: str          # returned only on registration — never again
    org_id: UUID


class AgentHeartbeatRequest(BaseModel):
    status: str           # ONLINE | IDLE | RUNNING
    current_parallel_sessions: Optional[int] = None
    agent_version: Optional[str] = None
    browser_versions: Optional[dict] = None
    tags: Optional[list[str]] = None


class AgentResponse(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    hostname: Optional[str]
    os_version: Optional[str]
    agent_version: Optional[str]
    protocol_version: Optional[int]
    payload_versions_supported: Optional[list]
    browser_versions: Optional[dict]
    installed_apps: Optional[list]
    tags: Optional[list]
    capabilities: Optional[dict]
    max_parallel_sessions: int
    current_parallel_sessions: int
    status: str
    last_heartbeat: Optional[str]

    model_config = {"from_attributes": True}

    def model_post_init(self, __context):
        if self.last_heartbeat and hasattr(self.last_heartbeat, "isoformat"):
            self.last_heartbeat = self.last_heartbeat.isoformat()


# ── Helper — resolve agent from API key header ────────────────────────────────

def get_agent_from_api_key(
    x_agent_api_key: str = Header(..., alias=settings.AGENT_API_KEY_HEADER),
    db: Session = Depends(get_db),
):
    repo = AgentRepository(db)
    hashed = AgentRepository.hash_api_key(x_agent_api_key)
    agent = repo.get_by_api_key_hash(hashed)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent API key")
    return agent


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=AgentRegisterResponse,
             dependencies=[Depends(require_role("ADMIN"))])
def register_agent(
    body: AgentRegisterRequest,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    """ADMIN creates an agent record and receives the API key once."""
    repo = AgentRepository(db)
    raw_key, hashed_key = AgentRepository.generate_api_key()

    agent = repo.create_agent(
        org_id=current_user.org_id,
        name=body.name,
        api_key_hash=hashed_key,
        max_parallel_sessions=body.max_parallel_sessions,
    )

    # Store capability fields if provided at registration time
    agent.hostname = body.hostname
    agent.os_version = body.os_version
    agent.agent_version = body.agent_version
    agent.protocol_version = body.protocol_version
    agent.payload_versions_supported = body.payload_versions_supported
    agent.browser_versions = body.browser_versions
    agent.installed_apps = body.installed_apps
    agent.tags = body.tags
    agent.capabilities = body.capabilities
    agent.host_info = body.host_info

    db.commit()
    db.refresh(agent)

    AuditEventRepository(db).write(
        org_id=current_user.org_id,
        entity_type="Agent",
        entity_id=agent.id,
        action="CREATED",
        actor_id=current_user.id,
    )
    db.commit()

    return AgentRegisterResponse(
        id=agent.id,
        name=agent.name,
        api_key=raw_key,      # only time raw key is returned
        org_id=agent.org_id,
    )


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def heartbeat(
    body: AgentHeartbeatRequest,
    agent=Depends(get_agent_from_api_key),
    db: Session = Depends(get_db),
):
    """Called by the agent every N seconds. Updates status and capacity."""
    repo = AgentRepository(db)
    repo.update_heartbeat(
        agent=agent,
        status=body.status,
        agent_version=body.agent_version,
        browser_versions=body.browser_versions,
        tags=body.tags,
        current_parallel_sessions=body.current_parallel_sessions,
    )
    db.commit()


@router.get("/", response_model=list[AgentResponse])
def list_agents(
    offset: int = 0,
    limit: int = 50,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = AgentRepository(db)
    return repo.list(current_user.org_id, offset=offset, limit=limit)


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(
    agent_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = AgentRepository(db)
    agent = repo.get(agent_id, current_user.org_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentResponse,
              dependencies=[Depends(require_role("ADMIN"))])
def update_agent(
    agent_id: UUID,
    body: dict,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = AgentRepository(db)
    agent = repo.get(agent_id, current_user.org_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    allowed = {"name", "tags", "max_parallel_sessions"}
    for key, value in body.items():
        if key in allowed:
            setattr(agent, key, value)

    db.commit()
    db.refresh(agent)

    AuditEventRepository(db).write(
        org_id=current_user.org_id,
        entity_type="Agent",
        entity_id=agent.id,
        action="UPDATED",
        actor_id=current_user.id,
    )
    db.commit()
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_role("ADMIN"))])
def delete_agent(
    agent_id: UUID,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
):
    repo = AgentRepository(db)
    agent = repo.soft_delete(agent_id, current_user.org_id, current_user.id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    db.commit()

    AuditEventRepository(db).write(
        org_id=current_user.org_id,
        entity_type="Agent",
        entity_id=agent_id,
        action="DELETED",
        actor_id=current_user.id,
    )
    db.commit()
