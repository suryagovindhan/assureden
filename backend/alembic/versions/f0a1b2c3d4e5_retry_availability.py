"""Persist the earliest dispatch time for delayed retries."""
from alembic import op
import sqlalchemy as sa

revision = "f0a1b2c3d4e5"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("test_runs", sa.Column("available_after", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("test_runs", "available_after")
