"""phase4_orchestration

Phase 4: Execution Orchestration

New tables:
  - scheduled_jobs
  - scheduled_run_history
  - retry_records

Alter existing tables:
  - test_runs: ADD preferred_agent_id, preferred_agent_expires_at
  - agent_sessions: ADD lease_id, started_by_poll_id; ADD FK execution_id → test_runs

Revision ID: c4f5d6e7f8a9
Revises: 1b665188447d
Create Date: 2026-07-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "c4f5d6e7f8a9"
down_revision: Union[str, None] = "1b665188447d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── scheduled_jobs ────────────────────────────────────────────────────────
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("test_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("environment_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Scheduling
        sa.Column("cron_expression", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_run_status", sa.String(20), nullable=True),
        # Run config
        sa.Column("priority", sa.String(10), nullable=False, server_default="NORMAL"),
        sa.Column("run_variables", sa.JSON(), nullable=True),
        # Retry policy
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_delay_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("backoff_multiplier", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("max_retry_delay", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column("retry_on_timeout", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("retry_on_failure", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("retry_on_network_error", sa.Boolean(), nullable=False, server_default="true"),
        # Dispatch
        sa.Column("max_dispatch_attempts", sa.Integer(), nullable=True),
        # Preferred agent
        sa.Column("preferred_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("preferred_agent_wait_seconds", sa.Integer(), nullable=False, server_default="300"),
        # Operational
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("miss_threshold_minutes", sa.Integer(), nullable=False, server_default="5"),
        # Audit
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"],
                                ondelete="RESTRICT", name="fk_schedule_env", use_alter=True),
        sa.ForeignKeyConstraint(["preferred_agent_id"], ["agents.id"],
                                ondelete="SET NULL", name="fk_schedule_agent", use_alter=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"],
                                ondelete="RESTRICT", name="fk_schedule_created_by", use_alter=True),
    )
    op.create_index("idx_scheduled_jobs_org",     "scheduled_jobs", ["org_id"])
    op.create_index("idx_scheduled_jobs_enabled", "scheduled_jobs", ["org_id", "next_run_at"])

    # ── scheduled_run_history ─────────────────────────────────────────────────
    op.create_table(
        "scheduled_run_history",
        sa.Column("id",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Snapshot at fire time
        sa.Column("test_case_version",   sa.Integer(), nullable=True),
        sa.Column("environment_version", sa.Integer(), nullable=True),
        sa.Column("priority",            sa.String(10), nullable=True),
        # Event
        sa.Column("triggered_at",  sa.DateTime(), nullable=False),
        sa.Column("status",        sa.String(20), nullable=False),
        sa.Column("trigger_error", sa.String(500), nullable=True),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["job_id"], ["scheduled_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["test_runs.id"],
                                ondelete="RESTRICT", name="fk_history_run", use_alter=True),
    )
    op.create_index("idx_schedule_history_job", "scheduled_run_history", ["job_id", "triggered_at"])
    op.create_index("idx_schedule_history_org", "scheduled_run_history", ["org_id"])
    op.create_index("idx_schedule_history_run", "scheduled_run_history", ["run_id"])

    # ── retry_records ─────────────────────────────────────────────────────────
    op.create_table(
        "retry_records",
        sa.Column("id",              postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id",          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("retry_run_id",    postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt",         sa.Integer(), nullable=False),
        sa.Column("delay_seconds",   sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason",          sa.String(50), nullable=False),
        sa.Column("triggered_at",    sa.DateTime(), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("original_run_id", "attempt", name="uq_retry_original_attempt"),
        sa.ForeignKeyConstraint(["original_run_id"], ["test_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["retry_run_id"],    ["test_runs.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_retry_records_original", "retry_records", ["original_run_id"])
    op.create_index("idx_retry_records_retry",    "retry_records", ["retry_run_id"])
    op.create_index("idx_retry_records_org",      "retry_records", ["org_id"])

    # ── test_runs: preferred agent columns ────────────────────────────────────
    op.add_column("test_runs",
        sa.Column("preferred_agent_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("test_runs",
        sa.Column("preferred_agent_expires_at", sa.DateTime(), nullable=True))
    op.create_foreign_key(
        "fk_run_preferred_agent", "test_runs", "agents",
        ["preferred_agent_id"], ["id"], use_alter=True,
    )

    # ── agent_sessions: lease tracking + FK wiring ────────────────────────────
    op.add_column("agent_sessions",
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_sessions",
        sa.Column("started_by_poll_id", postgresql.UUID(as_uuid=True), nullable=True))
    # Wire the previously deferred FK: execution_id → test_runs.id
    op.create_foreign_key(
        "fk_session_run", "agent_sessions", "test_runs",
        ["execution_id"], ["id"], use_alter=True,
    )


def downgrade() -> None:
    # Reverse in dependency order
    op.drop_constraint("fk_session_run",          "agent_sessions", type_="foreignkey")
    op.drop_column("agent_sessions", "started_by_poll_id")
    op.drop_column("agent_sessions", "lease_id")

    op.drop_constraint("fk_run_preferred_agent",  "test_runs", type_="foreignkey")
    op.drop_column("test_runs", "preferred_agent_expires_at")
    op.drop_column("test_runs", "preferred_agent_id")

    op.drop_index("idx_retry_records_org",      table_name="retry_records")
    op.drop_index("idx_retry_records_retry",    table_name="retry_records")
    op.drop_index("idx_retry_records_original", table_name="retry_records")
    op.drop_table("retry_records")

    op.drop_index("idx_schedule_history_run", table_name="scheduled_run_history")
    op.drop_index("idx_schedule_history_org", table_name="scheduled_run_history")
    op.drop_index("idx_schedule_history_job", table_name="scheduled_run_history")
    op.drop_table("scheduled_run_history")

    op.drop_index("idx_scheduled_jobs_enabled", table_name="scheduled_jobs")
    op.drop_index("idx_scheduled_jobs_org",     table_name="scheduled_jobs")
    op.drop_table("scheduled_jobs")
