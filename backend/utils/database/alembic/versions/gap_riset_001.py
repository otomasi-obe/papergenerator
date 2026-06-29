"""add gap_riset column to literature_items

Revision ID: gap_riset_001
Revises: merge_all_heads
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "gap_riset_001"
down_revision = "merge_all_heads"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "literature_items",
        sa.Column("gap_riset", sa.Text(), nullable=True, server_default=""),
    )


def downgrade():
    op.drop_column("literature_items", "gap_riset")
