"""merge heads

Revision ID: 9f53ec924f41
Revises: fix_schema_drift_2026, ix_aul_user_created
Create Date: 2026-07-19 11:09:20.130201

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f53ec924f41'
down_revision: Union[str, None] = ('fix_schema_drift_2026', 'ix_aul_user_created')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
