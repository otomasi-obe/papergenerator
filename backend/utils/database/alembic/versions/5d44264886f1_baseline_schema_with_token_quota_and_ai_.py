"""baseline schema with token quota and ai_jobs progress

Revision ID: 5d44264886f1
Revises:
Create Date: 2026-05-20

NO-OP baseline. Schema was already migrated manually via SQL before Alembic was
wired up. Use `alembic stamp 5d44264886f1` to mark this DB as current.
All future migrations go through `alembic revision --autogenerate`.
"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


revision = "5d44264886f1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
