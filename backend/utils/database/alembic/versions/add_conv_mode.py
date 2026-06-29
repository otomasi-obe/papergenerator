"""add mode column to conversations

Revision ID: add_conv_mode
Revises: b1de57988b40
Create Date: 2026-06-06

Schema changes:
- conversations: add `mode VARCHAR(30)` (nullable) column to persist chat mode
  across backend restarts, replacing the previous in-memory `_CONV_MODE` dict.
  Defaults to NULL which is interpreted as 'tier0' at runtime.
"""

from alembic import op
import sqlalchemy as sa


revision = "add_conv_mode"
down_revision = "b1de57988b40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(sa.Column("mode", sa.String(length=30), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_column("mode")
