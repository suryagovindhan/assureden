"""
models/artifacts.py — Phase 5: RunArtifact ORM model.

Stores metadata about artifacts uploaded by agents during test execution.
The artifact binary is stored in the configured StorageProvider
(see app/storage/). The model stores only the storage key, not the bytes.

Key layout (consistent with LocalStorageProvider):
  <org_id>/<run_id>/<artifact_type>/<filename>

  e.g. org_abc123/run_xyz789/screenshots/step_001.png

This maps directly to S3/GCS object keys for future migration.

Artifact types:
  SCREENSHOT — PNG/JPEG screen capture (per step)
  VIDEO      — WebM/MP4 full session recording
  LOG        — Execution log (plain text)
  HAR        — HTTP Archive (JSON)
  TRACE      — Playwright/Selenium trace (zip)
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


ARTIFACT_TYPES = ("SCREENSHOT", "VIDEO", "LOG", "HAR", "TRACE")


class RunArtifact(Base):
    __tablename__ = "run_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )

    # Org + run linkage
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Optional: pin to a specific step result for per-step screenshots
    step_result_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("step_results.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # Artifact classification
    artifact_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        doc="SCREENSHOT | VIDEO | LOG | HAR | TRACE",
    )

    # Storage
    storage_key: Mapped[str] = mapped_column(
        Text, nullable=False,
        doc="Opaque key resolved by the configured StorageProvider. "
            "Format: <org_id>/<run_id>/<artifact_type>/<filename>",
    )
    filename: Mapped[str] = mapped_column(
        String(255), nullable=False,
        doc="Original filename for Content-Disposition headers",
    )
    size_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0,
    )
    content_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="application/octet-stream",
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<RunArtifact id={self.id} run_id={self.run_id} "
            f"type={self.artifact_type} file={self.filename}>"
        )
