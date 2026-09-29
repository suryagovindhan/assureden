"""Preserve current flow content and enforce one revision per flow version."""
from alembic import op
import sqlalchemy as sa

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("uix_flow_revision", "asset_revisions",
                    ["org_id", "asset_id", "revision"], unique=True,
                    postgresql_where=sa.text("asset_type = 'Flow'"))
    # Historical versions cannot be reconstructed from overwritten rows.
    op.execute("""
        INSERT INTO asset_revisions
            (id, org_id, asset_type, asset_id, revision, snapshot, created_by, created_at)
        SELECT gen_random_uuid(), f.org_id, 'Flow', f.id, f.version,
            json_build_object('name', f.name, 'description', f.description,
                'tags', f.tags, 'checksum', f.checksum, 'steps', COALESCE((
                    SELECT json_agg(json_build_object(
                        'id', s.id, 'version', s.version, 'position', s.position,
                        'action', s.action, 'description', s.description,
                        'input_value', s.input_value, 'target_url', s.target_url,
                        'timeout_ms', s.timeout_ms, 'is_optional', s.is_optional,
                        'is_enabled', s.is_enabled, 'page_object_id', s.page_object_id
                    ) ORDER BY s.position) FROM flow_steps s
                    WHERE s.flow_id = f.id AND s.org_id = f.org_id AND s.deleted_at IS NULL
                ), '[]'::json)), COALESCE(f.updated_by, f.created_by), now()
        FROM flows f WHERE f.deleted_at IS NULL
        ON CONFLICT (org_id, asset_id, revision) WHERE asset_type = 'Flow' DO NOTHING
    """)


def downgrade():
    # Keep revision history; removing a constraint must not delete user history.
    op.drop_index("uix_flow_revision", table_name="asset_revisions")
