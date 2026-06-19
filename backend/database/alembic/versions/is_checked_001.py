"""add is_checked column to literature_items

Revision ID: is_checked_001
Revises: jsonb_migration_001
Create Date: 2026-06-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "is_checked_001"
down_revision = "jsonb_migration_001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "literature_items",
        sa.Column(
            "is_checked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade():
    op.drop_column("literature_items", "is_checked")