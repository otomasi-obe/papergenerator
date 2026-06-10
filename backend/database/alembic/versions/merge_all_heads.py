"""merge multiple migration heads into one

Revision ID: merge_all_heads
Revises: add_conv_mode, f0121a767d17, perf_idx_2026
Create Date: 2026-06-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "merge_all_heads"
down_revision: Union[str, tuple[str, ...], None] = (
    "add_conv_mode",
    "f0121a767d17",
    "perf_idx_2026",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
