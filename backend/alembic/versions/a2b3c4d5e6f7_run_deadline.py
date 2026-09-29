"""Persist a fixed execution deadline independent of lease renewals."""
from alembic import op
import sqlalchemy as sa

revision = "a2b3c4d5e6f7"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("test_runs", sa.Column("deadline_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE test_runs SET deadline_at = started_at + timeout_seconds * INTERVAL '1 second' "
               "WHERE status = 'RUNNING' AND started_at IS NOT NULL")


def downgrade():
    op.drop_column("test_runs", "deadline_at")
