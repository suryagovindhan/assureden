"""
models/foundation.py — All Phase 0 ORM models

Migration order follows FK dependency:
  Organization → User → Agent → AgentSession
  → AuditEvent → AssetRevision
  → Notification → Webhook
  → Role → Permission → RolePermission → UserRole
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer,
    String, Text, JSON,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow


# ── Helpers ──────────────────────────────────────────────────────────────────

def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ─────────────────────────────────────────────────────────────────────────────
# Organization
# ─────────────────────────────────────────────────────────────────────────────

class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        Index("idx_organizations_slug", "slug"),
    )

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name:       Mapped[str]       = mapped_column(String(100), nullable=False)
    slug:       Mapped[str]       = mapped_column(String(100), nullable=False, unique=True)
    is_active:  Mapped[bool]      = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime]  = mapped_column(DateTime, default=utcnow, nullable=False)

    # Soft delete
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", use_alter=True, name="fk_org_deleted_by"),
        nullable=True,
    )

    # Relationships
    users:  Mapped[list["User"]]  = relationship("User",  back_populates="organization",
                                                  foreign_keys="User.org_id")
    agents: Mapped[list["Agent"]] = relationship("Agent", back_populates="organization")


# ─────────────────────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("idx_users_org_id",      "org_id"),
        Index("idx_users_org_deleted",  "org_id", "deleted_at"),
        Index("idx_users_email",        "email"),
        Index("idx_users_username",     "username"),
    )

    id:              Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:          Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    username:        Mapped[str]       = mapped_column(String(80), nullable=False)
    email:           Mapped[str]       = mapped_column(String(150), nullable=False)
    hashed_password: Mapped[str]       = mapped_column(String(255), nullable=False)
    role:            Mapped[str]       = mapped_column(String(20), nullable=False, default="TESTER")
    # ADMIN | LEAD | TESTER | VIEWER
    is_active:       Mapped[bool]      = mapped_column(Boolean, default=True, nullable=False)
    created_at:      Mapped[datetime]  = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at:      Mapped[datetime]  = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Soft delete
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="users", foreign_keys=[org_id]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────────────────────────────────────

class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        Index("idx_agents_org_id",      "org_id"),
        Index("idx_agents_org_deleted",  "org_id", "deleted_at"),
        Index("idx_agents_org_status",   "org_id", "status"),
    )

    id:           Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:       Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name:         Mapped[str]       = mapped_column(String(100), nullable=False)
    api_key_hash: Mapped[str]       = mapped_column(String(255), nullable=False)

    # ── Identity & Version ────────────────────────────────────────
    hostname:                    Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    os_version:                  Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    agent_version:               Mapped[Optional[str]] = mapped_column(String(50),  nullable=True)
    protocol_version:            Mapped[Optional[int]] = mapped_column(Integer,      nullable=True)
    payload_versions_supported:  Mapped[Optional[list]] = mapped_column(JSON,        nullable=True)
    # e.g. [1, 2]

    # ── Capabilities ──────────────────────────────────────────────
    browser_versions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # e.g. {"chromium": "120.0", "firefox": "121.0"}
    installed_apps:   Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    tags:             Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # stored as JSON array ["windows","cyberark"] — ARRAY(String) for GIN index in v2
    capabilities:     Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    host_info:        Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # ── Capacity Tracking ─────────────────────────────────────────
    max_parallel_sessions:     Mapped[int]               = mapped_column(Integer, default=1, nullable=False)
    current_parallel_sessions: Mapped[int]               = mapped_column(Integer, default=0, nullable=False)
    last_capacity_update:      Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ── Runtime State ─────────────────────────────────────────────
    status:         Mapped[str]               = mapped_column(String(20), default="OFFLINE", nullable=False)
    # ONLINE | IDLE | RUNNING | OFFLINE
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at:     Mapped[datetime]           = mapped_column(DateTime, default=utcnow, nullable=False)

    # Soft delete
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="agents")
    sessions:     Mapped[list["AgentSession"]] = relationship("AgentSession", back_populates="agent")


# ─────────────────────────────────────────────────────────────────────────────
# AgentSession
# ─────────────────────────────────────────────────────────────────────────────

class AgentSession(Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (
        Index("idx_agent_sessions_agent",     "agent_id"),
        Index("idx_agent_sessions_execution", "execution_id"),
        Index("idx_agent_sessions_org",       "org_id"),
    )

    id:           Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:       Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    # FK to executions.id added in Phase 6 migration — nullable here intentionally

    started_at:       Mapped[datetime]           = mapped_column(DateTime, default=utcnow, nullable=False)
    ended_at:         Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status:           Mapped[str]                = mapped_column(String(20), default="ACTIVE", nullable=False)
    # ACTIVE | COMPLETED | CRASHED | TIMED_OUT | DISCONNECTED
    session_log_path: Mapped[Optional[str]]      = mapped_column(String(500), nullable=True)

    agent: Mapped["Agent"] = relationship("Agent", back_populates="sessions")


# ─────────────────────────────────────────────────────────────────────────────
# AuditEvent  (metadata only — no inline snapshots)
# ─────────────────────────────────────────────────────────────────────────────

class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("idx_audit_org_entity",    "org_id", "entity_type", "entity_id"),
        Index("idx_audit_org_timestamp", "org_id", "timestamp"),
        Index("idx_audit_actor",         "actor_id"),
    )

    id:          Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:      Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_id:    Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    # NULL = SYSTEM action

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id:   Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    action: Mapped[str] = mapped_column(String(60), nullable=False)
    # CREATED | UPDATED | DELETED | RESTORED | STATUS_CHANGED | PROMOTED
    # APPROVED | DEPRECATED | ARCHIVED | LOCATOR_PROMOTED
    # DEPENDENCY_REBUILT | REVISION_CREATED | EXECUTION_TRIGGERED
    # DISPATCHED | TIMED_OUT | ABORTED | QUEUE_POSITION_CHANGED
    # ROW_RESERVED | ROW_RELEASED | SECRET_ROTATED
    # SESSION_STARTED | SESSION_ENDED | SESSION_CRASHED
    # CAPACITY_UPDATED | AGENT_VERSION_MISMATCH

    revision_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    # FK to asset_revisions.id — populated when a snapshot was taken

    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# ─────────────────────────────────────────────────────────────────────────────
# AssetRevision  (full snapshots live here, never in AuditEvent)
# ─────────────────────────────────────────────────────────────────────────────

class AssetRevision(Base):
    __tablename__ = "asset_revisions"
    __table_args__ = (
        Index("idx_revisions_asset", "asset_type", "asset_id"),
        Index("idx_revisions_org",   "org_id"),
    )

    id:             Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:         Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), nullable=False)
    asset_type:     Mapped[str]              = mapped_column(String(100), nullable=False)
    asset_id:       Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), nullable=False)
    revision:       Mapped[int]              = mapped_column(Integer, nullable=False)
    snapshot:       Mapped[dict]             = mapped_column(JSON, nullable=False)
    change_summary: Mapped[Optional[str]]    = mapped_column(String(500), nullable=True)
    created_by:     Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at:     Mapped[datetime]         = mapped_column(DateTime, default=utcnow, nullable=False)


# ─────────────────────────────────────────────────────────────────────────────
# Notification  (reserved schema — business logic wired in Phase 12)
# ─────────────────────────────────────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_user",    "user_id"),
        Index("idx_notifications_org",     "org_id"),
        Index("idx_notifications_unread",  "user_id", "is_read"),
    )

    id:         Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:     Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id:    Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    type:       Mapped[str]              = mapped_column(String(80), nullable=False)
    # EXECUTION_FAILED | APPROVAL_REQUIRED | AGENT_OFFLINE | SECRET_EXPIRING
    # LOCATOR_DEGRADED | DEPENDENCY_HIGH_RISK | VALIDATION_DECAY
    title:      Mapped[str]              = mapped_column(String(255), nullable=False)
    payload:    Mapped[Optional[dict]]   = mapped_column(JSON, nullable=True)
    is_read:    Mapped[bool]             = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime]         = mapped_column(DateTime, default=utcnow, nullable=False)


# ─────────────────────────────────────────────────────────────────────────────
# Webhook  (reserved schema — wired in Phase 14)
# ─────────────────────────────────────────────────────────────────────────────

class Webhook(Base):
    __tablename__ = "webhooks"
    __table_args__ = (
        Index("idx_webhooks_org", "org_id"),
    )

    id:         Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:     Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), nullable=False)
    name:       Mapped[str]              = mapped_column(String(100), nullable=False)
    event_type: Mapped[str]              = mapped_column(String(80), nullable=False)
    # EXECUTION_FAILED | APPROVAL_REQUIRED | AGENT_OFFLINE | ...
    target_url: Mapped[str]              = mapped_column(String(500), nullable=False)
    secret:     Mapped[Optional[str]]    = mapped_column(String(255), nullable=True)
    is_enabled: Mapped[bool]             = mapped_column(Boolean, default=True, nullable=False)
    headers:    Mapped[Optional[dict]]   = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime]         = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime]         = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Soft delete
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


# ─────────────────────────────────────────────────────────────────────────────
# RBAC  (reserved schema — wired in Phase 14)
# ─────────────────────────────────────────────────────────────────────────────

class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        Index("idx_roles_org", "org_id"),
    )

    id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:     Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name:       Mapped[str]       = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime]  = mapped_column(DateTime, default=utcnow, nullable=False)

    permissions: Mapped[list["RolePermission"]] = relationship("RolePermission", back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"

    id:       Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    resource: Mapped[str]       = mapped_column(String(100), nullable=False)
    # PAGE_OBJECT | ACTION | FLOW | TEST_CASE | ENVIRONMENT | ...
    action:   Mapped[str]       = mapped_column(String(20), nullable=False)
    # CREATE | READ | UPDATE | DELETE | EXECUTE


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id:       Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("permissions.id"), primary_key=True)

    role: Mapped["Role"] = relationship("Role", back_populates="permissions")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        Index("idx_user_roles_user", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True)
