"""Merge orchestration and artifact migration branches.

Both branches are retained so databases already on either branch upgrade safely.
"""

revision = "e8f9a0b1c2d3"
down_revision = ("c4f5d6e7f8a9", "d7e8f9a0b1c2")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
