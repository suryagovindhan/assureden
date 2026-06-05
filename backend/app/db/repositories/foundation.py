"""
db/repositories/foundation.py — Concrete repos for all Phase 0 entities
"""

import hashlib
import secrets
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.repositories.base import OrgScopedRepository, BaseRepository
from app.models.foundation import (
    Organization, User, Agent, AgentSession,
    AuditEvent, AssetRevision,
)


# ── Organization ──────────────────────────────────────────────────────────────

class OrganizationRepository(OrgScopedRepository[Organization]):
    model = Organization

    def get_by_slug(self, slug: str) -> Optional[Organization]:
        stmt = select(Organization).where(
            Organization.slug == slug,
            Organization.deleted_at.is_(None),
        )
        return self.db.scalar(stmt)

    def create_org(self, name: str, slug: str) -> Organization:
        return self.create(name=name, slug=slug)


# ── User ──────────────────────────────────────────────────────────────────────

class UserRepository(OrgScopedRepository[User]):
    model = User

    def get_by_email(self, email: str, org_id: UUID) -> Optional[User]:
        stmt = select(User).where(
            User.email == email,
            User.org_id == org_id,
            User.deleted_at.is_(None),
        )
        return self.db.scalar(stmt)

    def get_by_username(self, username: str, org_id: UUID) -> Optional[User]:
        stmt = select(User).where(
            User.username == username,
            User.org_id == org_id,
            User.deleted_at.is_(None),
        )
        return self.db.scalar(stmt)

    def create_user(
        self,
        org_id: UUID,
        username: str,
        email: str,
        hashed_password: str,
        role: str = "TESTER",
    ) -> User:
        return self.create(
            org_id=org_id,
            username=username,
            email=email,
            hashed_password=hashed_password,
            role=role,
        )


# ── Agent ─────────────────────────────────────────────────────────────────────

class AgentRepository(OrgScopedRepository[Agent]):
    model = Agent

    # ── API Key Management ────────────────────────────────────────
    @staticmethod
    def generate_api_key() -> tuple[str, str]:
        """Returns (raw_key, hashed_key). Store only the hash."""
        raw = secrets.token_urlsafe(32)
        hashed = hashlib.sha256(raw.encode()).hexdigest()
        return raw, hashed

    @staticmethod
    def hash_api_key(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    def get_by_api_key_hash(self, api_key_hash: str) -> Optional[Agent]:
        stmt = select(Agent).where(
            Agent.api_key_hash == api_key_hash,
            Agent.deleted_at.is_(None),
        )
        return self.db.scalar(stmt)

    def create_agent(
        self,
        org_id: UUID,
        name: str,
        api_key_hash: str,
        max_parallel_sessions: int = 1,
    ) -> Agent:
        return self.create(
            org_id=org_id,
            name=name,
            api_key_hash=api_key_hash,
            max_parallel_sessions=max_parallel_sessions,
            current_parallel_sessions=0,
            status="OFFLINE",
        )

    def update_heartbeat(
        self,
        agent: Agent,
        status: str,
        host_info: Optional[dict] = None,
        browser_versions: Optional[dict] = None,
        installed_apps: Optional[list] = None,
        agent_version: Optional[str] = None,
        protocol_version: Optional[int] = None,
        payload_versions_supported: Optional[list] = None,
        tags: Optional[list] = None,
        current_parallel_sessions: Optional[int] = None,
    ) -> Agent:
        agent.last_heartbeat = utcnow()
        agent.last_capacity_update = utcnow()
        agent.status = status
        if host_info is not None:
            agent.host_info = host_info
        if browser_versions is not None:
            agent.browser_versions = browser_versions
        if installed_apps is not None:
            agent.installed_apps = installed_apps
        if agent_version is not None:
            agent.agent_version = agent_version
        if protocol_version is not None:
            agent.protocol_version = protocol_version
        if payload_versions_supported is not None:
            agent.payload_versions_supported = payload_versions_supported
        if tags is not None:
            agent.tags = tags
        if current_parallel_sessions is not None:
            agent.current_parallel_sessions = current_parallel_sessions
        self.db.flush()
        return agent

    def get_available_by_tags(
        self,
        org_id: UUID,
        required_tags: list[str],
        limit: int = 10,
    ) -> list[Agent]:
        """Returns agents that are ONLINE/IDLE, have capacity, and carry all required tags.
        Full GIN-index tag matching is a v2 optimisation; this is correct for v1 volumes."""
        candidates = self.list(org_id, status="IDLE", limit=100)
        candidates += self.list(org_id, status="ONLINE", limit=100)
        result = []
        seen = set()
        for agent in candidates:
            if agent.id in seen:
                continue
            if agent.current_parallel_sessions >= agent.max_parallel_sessions:
                continue
            agent_tags = set(agent.tags or [])
            if all(t in agent_tags for t in required_tags):
                result.append(agent)
                seen.add(agent.id)
        return result[:limit]


# ── AgentSession ──────────────────────────────────────────────────────────────

class AgentSessionRepository(BaseRepository[AgentSession]):
    model = AgentSession

    def create_session(self, org_id: UUID, agent_id: UUID, execution_id: Optional[UUID] = None) -> AgentSession:
        return self.create(org_id=org_id, agent_id=agent_id, execution_id=execution_id)

    def get_active_for_agent(self, agent_id: UUID) -> list[AgentSession]:
        stmt = select(AgentSession).where(
            AgentSession.agent_id == agent_id,
            AgentSession.status == "ACTIVE",
        )
        return list(self.db.scalars(stmt).all())

    def end_session(self, session: AgentSession, status: str = "COMPLETED") -> AgentSession:
        session.ended_at = utcnow()
        session.status = status
        self.db.flush()
        return session


# ── AuditEvent ────────────────────────────────────────────────────────────────

class AuditEventRepository(BaseRepository[AuditEvent]):
    model = AuditEvent

    def write(
        self,
        org_id: UUID,
        entity_type: str,
        entity_id: UUID,
        action: str,
        actor_id: Optional[UUID] = None,
        revision_id: Optional[UUID] = None,
    ) -> AuditEvent:
        return self.create(
            org_id=org_id,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            revision_id=revision_id,
        )

    def list_for_entity(
        self,
        org_id: UUID,
        entity_type: str,
        entity_id: UUID,
        limit: int = 50,
    ) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(
                AuditEvent.org_id == org_id,
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id,
            )
            .order_by(AuditEvent.timestamp.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())


# ── AssetRevision ─────────────────────────────────────────────────────────────

class AssetRevisionRepository(BaseRepository[AssetRevision]):
    model = AssetRevision

    def latest_for(self, asset_type: str, asset_id: UUID, org_id: UUID) -> Optional[AssetRevision]:
        stmt = (
            select(AssetRevision)
            .where(
                AssetRevision.org_id == org_id,
                AssetRevision.asset_type == asset_type,
                AssetRevision.asset_id == asset_id,
            )
            .order_by(AssetRevision.revision.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def snapshot(
        self,
        org_id: UUID,
        asset_type: str,
        asset_id: UUID,
        snapshot: dict,
        change_summary: str,
        created_by: Optional[UUID],
    ) -> AssetRevision:
        latest = self.latest_for(asset_type, asset_id, org_id)
        next_rev = (latest.revision + 1) if latest else 1
        return self.create(
            org_id=org_id,
            asset_type=asset_type,
            asset_id=asset_id,
            revision=next_rev,
            snapshot=snapshot,
            change_summary=change_summary,
            created_by=created_by,
        )

    def list_for_asset(
        self,
        org_id: UUID,
        asset_type: str,
        asset_id: UUID,
        limit: int = 20,
    ) -> list[AssetRevision]:
        stmt = (
            select(AssetRevision)
            .where(
                AssetRevision.org_id == org_id,
                AssetRevision.asset_type == asset_type,
                AssetRevision.asset_id == asset_id,
            )
            .order_by(AssetRevision.revision.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())
