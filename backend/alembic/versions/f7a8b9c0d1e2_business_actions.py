"""Classify reusable assets while sharing canonical steps and revisions."""
from alembic import op
import sqlalchemy as sa
revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("flows", sa.Column("kind", sa.String(20), nullable=False, server_default="FLOW"))
    op.create_check_constraint("ck_flows_kind", "flows", "kind IN ('FLOW', 'BUSINESS_ACTION')")

def downgrade():
    op.drop_constraint("ck_flows_kind", "flows", type_="check")
    op.drop_column("flows", "kind")
