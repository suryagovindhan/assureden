"""Track the reusable flow created from a reviewed draft."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("draft_assets", sa.Column("promoted_flow_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_draft_promoted_flow", "draft_assets", "flows", ["promoted_flow_id"], ["id"])

def downgrade():
    op.drop_constraint("fk_draft_promoted_flow", "draft_assets", type_="foreignkey")
    op.drop_column("draft_assets", "promoted_flow_id")
