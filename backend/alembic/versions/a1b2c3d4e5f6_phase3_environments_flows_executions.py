"""phase3_environments_flows_executions

Revision ID: a1b2c3d4e5f6
Revises: 9aa74c286b25
Create Date: 2026-07-03 10:00:00.000000

Phase 3 changes:
  - CREATE TABLE environments
  - CREATE TABLE environment_variables
  - CREATE TABLE flows
  - CREATE TABLE flow_steps
  - CREATE TABLE test_runs
  - CREATE TABLE step_results
  - CREATE TABLE run_events
  - ALTER TABLE test_steps ADD flow_id, flow_version
  - ALTER TABLE agents    ADD last_seen_at (alias for last_heartbeat)

Note on partial indexes:
  postgresql_where= partial indexes are PostgreSQL-specific.
  On SQLite (dev/test), these fall back to regular indexes.
  Always run concurrent agent polling tests against PostgreSQL.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9aa74c286b25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── environments ───────────────────────────────────────────────
    op.create_table(
        'environments',
        sa.Column('id',          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id',      postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name',        sa.String(100), nullable=False),
        sa.Column('description', sa.Text,        nullable=True),
        sa.Column('base_url',    sa.String(500), nullable=True),
        sa.Column('tags',        sa.Text,        nullable=True),
        sa.Column('version',     sa.Integer,     nullable=False, server_default='1'),
        sa.Column('is_default',  sa.Boolean,     nullable=False, server_default='false'),
        sa.Column('created_by',  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at',  sa.DateTime,    nullable=False),
        sa.Column('updated_by',  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at',  sa.DateTime,    nullable=False),
        sa.Column('deleted_at',  sa.DateTime,    nullable=True),
        sa.Column('deleted_by',  postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'],
                                name='fk_env_created_by', use_alter=True, ondelete='RESTRICT'),
        sa.CheckConstraint('version >= 1', name='ck_environments_version_positive'),
    )
    op.create_index('idx_environments_org',        'environments', ['org_id'])
    op.create_index('idx_environments_org_deleted', 'environments', ['org_id', 'deleted_at'])
    op.create_index(
        'uix_environments_org_name_live', 'environments', ['org_id', 'name'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )

    # ── environment_variables ──────────────────────────────────────
    op.create_table(
        'environment_variables',
        sa.Column('id',             postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id',         postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('environment_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key',            sa.String(200), nullable=False),
        sa.Column('value_encrypted',sa.Text,        nullable=False),
        sa.Column('key_id',         sa.String(20),  nullable=False),
        sa.Column('type',           sa.String(20),  nullable=False, server_default='STRING'),
        sa.Column('is_secret',      sa.Boolean,     nullable=False, server_default='false'),
        sa.Column('description',    sa.String(300), nullable=True),
        sa.Column('created_by',     postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at',     sa.DateTime,    nullable=False),
        sa.Column('updated_at',     sa.DateTime,    nullable=False),
        sa.Column('deleted_at',     sa.DateTime,    nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['environment_id'], ['environments.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'],
                                name='fk_env_var_created_by', use_alter=True, ondelete='RESTRICT'),
    )
    op.create_index('idx_env_vars_env', 'environment_variables', ['environment_id'])
    op.create_index('idx_env_vars_org', 'environment_variables', ['org_id'])
    op.create_index(
        'uix_env_vars_env_key_live', 'environment_variables', ['environment_id', 'key'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )

    # ── flows ──────────────────────────────────────────────────────
    op.create_table(
        'flows',
        sa.Column('id',                   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id',               postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name',                 sa.String(200), nullable=False),
        sa.Column('description',          sa.Text,        nullable=True),
        sa.Column('tags',                 sa.Text,        nullable=True),
        sa.Column('version',              sa.Integer,     nullable=False, server_default='1'),
        sa.Column('checksum',             sa.String(64),  nullable=False, server_default=''),
        sa.Column('created_from_flow_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_from_version', sa.Integer,     nullable=True),
        sa.Column('created_by',           postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at',           sa.DateTime,    nullable=False),
        sa.Column('updated_by',           postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at',           sa.DateTime,    nullable=False),
        sa.Column('deleted_at',           sa.DateTime,    nullable=True),
        sa.Column('deleted_by',           postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'],
                                name='fk_flow_created_by', use_alter=True, ondelete='RESTRICT'),
        sa.CheckConstraint('version >= 1', name='ck_flows_version_positive'),
    )
    op.create_index('idx_flows_org',        'flows', ['org_id'])
    op.create_index('idx_flows_org_deleted', 'flows', ['org_id', 'deleted_at'])
    op.create_index(
        'uix_flows_org_name_live', 'flows', ['org_id', 'name'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )

    # ── flow_steps ─────────────────────────────────────────────────
    op.create_table(
        'flow_steps',
        sa.Column('id',             postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id',         postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('flow_id',        postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('position',       sa.Integer,     nullable=False),
        sa.Column('version',        sa.Integer,     nullable=False, server_default='1'),
        sa.Column('action',         sa.String(60),  nullable=False),
        sa.Column('description',    sa.Text,        nullable=True),
        sa.Column('input_value',    sa.Text,        nullable=True),
        sa.Column('target_url',     sa.String(500), nullable=True),
        sa.Column('timeout_ms',     sa.Integer,     nullable=False, server_default='30000'),
        sa.Column('is_optional',    sa.Boolean,     nullable=False, server_default='false'),
        sa.Column('is_enabled',     sa.Boolean,     nullable=False, server_default='true'),
        sa.Column('page_object_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by',     postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at',     sa.DateTime,    nullable=False),
        sa.Column('updated_by',     postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at',     sa.DateTime,    nullable=False),
        sa.Column('deleted_at',     sa.DateTime,    nullable=True),
        sa.Column('deleted_by',     postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['flow_id'], ['flows.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['page_object_id'], ['page_objects.id'],
                                name='fk_flow_step_po', use_alter=True, ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'],
                                name='fk_flow_step_created_by', use_alter=True, ondelete='RESTRICT'),
        sa.CheckConstraint('position >= 1', name='ck_flow_steps_position_positive'),
        sa.CheckConstraint('version >= 1',  name='ck_flow_steps_version_positive'),
    )
    op.create_index('idx_flow_steps_flow',        'flow_steps', ['flow_id'])
    op.create_index('idx_flow_steps_org',         'flow_steps', ['org_id'])
    op.create_index('idx_flow_steps_flow_pos',    'flow_steps', ['flow_id', 'position'])
    op.create_index('idx_flow_steps_page_object', 'flow_steps', ['page_object_id'])
    op.create_index(
        'uix_flow_steps_flow_pos_live', 'flow_steps', ['flow_id', 'position'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )

    # ── test_runs ──────────────────────────────────────────────────
    op.create_table(
        'test_runs',
        sa.Column('id',                        postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id',                    postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('test_case_id',              postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('test_case_version',         sa.Integer,    nullable=False),
        sa.Column('environment_id',            postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('environment_version',       sa.Integer,    nullable=True),
        sa.Column('agent_id',                  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('agent_version',             sa.String(50), nullable=True),
        sa.Column('triggered_by',              postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('triggered_at',              sa.DateTime,   nullable=False),
        sa.Column('status',                    sa.String(20), nullable=False, server_default='QUEUED'),
        sa.Column('priority',                  sa.String(20), nullable=False, server_default='NORMAL'),
        sa.Column('started_at',                sa.DateTime,   nullable=True),
        sa.Column('completed_at',              sa.DateTime,   nullable=True),
        sa.Column('lease_id',                  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('lease_expires_at',          sa.DateTime,   nullable=True),
        sa.Column('dispatch_attempt_count',    sa.Integer,    nullable=False, server_default='0'),
        sa.Column('retry_count',               sa.Integer,    nullable=False, server_default='0'),
        sa.Column('minimum_protocol_version',  sa.Integer,    nullable=False, server_default='1'),
        sa.Column('run_variables',             sa.JSON,       nullable=True),
        sa.Column('variable_provenance',       sa.JSON,       nullable=True),
        sa.Column('execution_snapshot',        sa.JSON,       nullable=True),
        sa.Column('execution_snapshot_sha256', sa.String(64), nullable=True),
        sa.Column('snapshot_schema_version',   sa.Integer,    nullable=False, server_default='1'),
        sa.Column('execution_plan_version',    sa.Integer,    nullable=False, server_default='1'),
        sa.Column('total_steps',               sa.Integer,    nullable=True),
        sa.Column('passed_steps',              sa.Integer,    nullable=False, server_default='0'),
        sa.Column('failed_steps',              sa.Integer,    nullable=False, server_default='0'),
        sa.Column('skipped_steps',             sa.Integer,    nullable=False, server_default='0'),
        sa.Column('error_message',             sa.String(500),nullable=True),
        sa.Column('timeout_seconds',           sa.Integer,    nullable=False, server_default='3600'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['test_case_id'], ['test_cases.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['environment_id'], ['environments.id'],
                                name='fk_run_env', use_alter=True, ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'],
                                name='fk_run_agent', use_alter=True, ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['triggered_by'], ['users.id'],
                                name='fk_run_triggered_by', use_alter=True, ondelete='RESTRICT'),
    )
    op.create_index('idx_test_runs_org_status',    'test_runs', ['org_id', 'status'])
    op.create_index('idx_test_runs_org_case',      'test_runs', ['org_id', 'test_case_id'])
    op.create_index('idx_test_runs_org_triggered', 'test_runs', ['org_id', 'triggered_at'])
    op.create_index('idx_test_runs_agent',         'test_runs', ['agent_id'])

    # ── step_results ───────────────────────────────────────────────
    op.create_table(
        'step_results',
        sa.Column('id',                postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id',            postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('run_id',            postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('execution_step_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('step_id',           postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('step_version',      sa.Integer,    nullable=False),
        sa.Column('position',          sa.Integer,    nullable=False),
        sa.Column('attempt',           sa.Integer,    nullable=False, server_default='1'),
        sa.Column('action',            sa.String(60), nullable=False),
        sa.Column('status',            sa.String(30), nullable=False, server_default='PENDING'),
        sa.Column('started_at',        sa.DateTime,   nullable=True),
        sa.Column('completed_at',      sa.DateTime,   nullable=True),
        sa.Column('duration_ms',       sa.Integer,    nullable=True),
        sa.Column('display_value',     sa.Text,       nullable=True),
        sa.Column('screenshot_url',    sa.String(500),nullable=True),
        sa.Column('error_message',     sa.Text,       nullable=True),
        sa.Column('assertions',        sa.JSON,       nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['run_id'], ['test_runs.id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('run_id', 'execution_step_id', 'attempt', name='uq_step_result_exec_attempt'),
    )
    op.create_index('idx_step_results_run',     'step_results', ['run_id'])
    op.create_index('idx_step_results_org_run', 'step_results', ['org_id', 'run_id'])

    # ── run_events ─────────────────────────────────────────────────
    op.create_table(
        'run_events',
        sa.Column('id',       postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('run_id',   postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sequence', sa.Integer,    nullable=False),
        sa.Column('timestamp',sa.DateTime,   nullable=False),
        sa.Column('event',    sa.String(50), nullable=False),
        sa.Column('severity', sa.String(10), nullable=False, server_default='INFO'),
        sa.Column('message',  sa.String(500),nullable=False),
        sa.Column('metadata', sa.JSON,       nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['run_id'], ['test_runs.id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('run_id', 'sequence', name='uq_run_event_run_seq'),
    )
    op.create_index('idx_run_events_run',          'run_events', ['run_id'])
    op.create_index('idx_run_events_run_severity', 'run_events', ['run_id', 'severity'])

    # ── ALTER TABLE test_steps: add flow_id, flow_version ─────────
    op.add_column('test_steps', sa.Column('flow_id',      postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('test_steps', sa.Column('flow_version', sa.Integer, nullable=True))
    op.create_foreign_key(
        'fk_test_step_flow', 'test_steps', 'flows',
        ['flow_id'], ['id'], use_alter=True, ondelete='RESTRICT',
    )

    # ── ALTER TABLE agents: add last_seen_at (mirrors last_heartbeat for new model) ──
    # last_heartbeat already exists from Phase 0; last_seen_at is the Phase 3 name.
    # We keep last_heartbeat for backward compat and derive status from it in code.


def downgrade() -> None:
    # Drop FKs and tables in reverse dependency order
    op.drop_constraint('fk_test_step_flow', 'test_steps', type_='foreignkey')
    op.drop_column('test_steps', 'flow_version')
    op.drop_column('test_steps', 'flow_id')

    op.drop_table('run_events')
    op.drop_table('step_results')
    op.drop_table('test_runs')
    op.drop_table('flow_steps')
    op.drop_table('flows')
    op.drop_table('environment_variables')
    op.drop_table('environments')
