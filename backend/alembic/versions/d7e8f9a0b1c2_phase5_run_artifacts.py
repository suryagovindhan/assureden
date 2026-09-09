"""Phase 5: run_artifacts table

Revision ID: d7e8f9a0b1c2
Revises: 1b665188447d
Create Date: 2026-08-05

Adds the run_artifacts table for Phase 5 artifact storage.
Binary data lives in the configured StorageProvider (local/.artifacts/,
or future S3/GCS). This table stores only metadata + the storage key.

Key layout: <org_id>/<run_id>/<artifact_type>/<filename>
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d7e8f9a0b1c2"
down_revision = "1b665188447d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_artifacts",
        sa.Column("id",             postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id",         postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id",         postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("artifact_type",  sa.String(20),  nullable=False),
        sa.Column("storage_key",    sa.Text(),       nullable=False),
        sa.Column("filename",       sa.String(255),  nullable=False),
        sa.Column("size_bytes",     sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("content_type",   sa.String(100),  nullable=False, server_default="application/octet-stream"),
        sa.Column("created_at",     sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),

        sa.ForeignKeyConstraint(["org_id"],         ["organizations.id"]),
        sa.ForeignKeyConstraint(["run_id"],          ["test_runs.id"],     ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_result_id"],  ["step_results.id"],  ondelete="SET NULL"),
    )

    # Indexes for the most common access patterns
    op.create_index("ix_run_artifacts_run_id",  "run_artifacts", ["run_id"])
    op.create_index("ix_run_artifacts_org_id",  "run_artifacts", ["org_id"])
    op.create_index("ix_run_artifacts_step_result_id", "run_artifacts", ["step_result_id"])


def downgrade() -> None:
    op.drop_index("ix_run_artifacts_step_result_id", table_name="run_artifacts")
    op.drop_index("ix_run_artifacts_org_id",  table_name="run_artifacts")
    op.drop_index("ix_run_artifacts_run_id",  table_name="run_artifacts")
    op.drop_table("run_artifacts")
