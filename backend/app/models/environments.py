"""
models/environments.py — Phase 3: Environment and EnvironmentVariable ORM models

Environment:
  - Soft-deleted, org-scoped
  - version increments on ANY semantic change (variables or metadata)
  - environment_version in TestRun is informational; snapshot is truth

EnvironmentVariable:
  - value_encrypted: Fernet ciphertext
  - key_id: identifies which encryption key was used (rotation support)
  - type: data type (STRING | NUMBER | BOOLEAN | JSON) — orthogonal to is_secret
  - is_secret: storage/masking policy — true → value masked in reads as ****
  - Keys are case-sensitive; case-insensitive uniqueness enforced at repository write time
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index,
    Integer, String, Text, UniqueConstraint,
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class VariableType(str, enum.Enum):
    STRING  = "STRING"
    NUMBER  = "NUMBER"
    BOOLEAN = "BOOLEAN"
    JSON    = "JSON"


_variable_type_t = SAEnum(VariableType, native_enum=False, validate_strings=True, name="variable_type")


class Environment(Base):
    """Named execution context (e.g. 'staging', 'production')."""
    __tablename__ = "environments"
    __table_args__ = (
        Index("idx_environments_org",         "org_id"),
        Index("idx_environments_org_deleted",  "org_id", "deleted_at"),
        # Partial unique index on (org_id, name) excluding deleted rows
        Index(
            "uix_environments_org_name_live",
            "org_id", "name",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        CheckConstraint("version >= 1", name="ck_environments_version_positive"),
    )

    id:          Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:      Mapped[uuid.UUID]      = mapped_column(UUID(as_uuid=True), nullable=False)
    name:        Mapped[str]            = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]]  = mapped_column(Text, nullable=True)
    base_url:    Mapped[Optional[str]]  = mapped_column(String(500), nullable=True)
    tags:        Mapped[Optional[list]] = mapped_column("tags", Text, nullable=True)
    # tags stored as JSON string to avoid dialect-specific ARRAY type
    version:     Mapped[int]            = mapped_column(Integer, nullable=False, default=1)
    is_default:  Mapped[bool]           = mapped_column(Boolean, nullable=False, default=False)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", use_alter=True, ondelete="RESTRICT", name="fk_env_created_by"),
        nullable=True,
    )
    created_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime]            = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]]  = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    variables: Mapped[list["EnvironmentVariable"]] = relationship(
        "EnvironmentVariable", back_populates="environment",
    )


class EnvironmentVariable(Base):
    """Key/value pair scoped to an environment. Values are always encrypted at rest."""
    __tablename__ = "environment_variables"
    __table_args__ = (
        Index("idx_env_vars_env",    "environment_id"),
        Index("idx_env_vars_org",    "org_id"),
        # Partial unique index on (environment_id, key) excluding deleted rows
        Index(
            "uix_env_vars_env_key_live",
            "environment_id", "key",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    id:             Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id:         Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="RESTRICT"), nullable=False,
    )

    key:             Mapped[str] = mapped_column(String(200), nullable=False)  # case-sensitive
    value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    key_id:          Mapped[str] = mapped_column(String(20), nullable=False)   # encryption key version

    type:      Mapped[str]  = mapped_column(_variable_type_t, nullable=False, default=VariableType.STRING)
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    description: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", use_alter=True, ondelete="RESTRICT", name="fk_env_var_created_by"),
        nullable=True,
    )
    created_at: Mapped[datetime]           = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime]           = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    environment: Mapped["Environment"] = relationship("Environment", back_populates="variables")
