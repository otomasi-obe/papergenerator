"""add composite index api_usage_logs(user_id, created_at)

Revision ID: ix_aul_user_created
Revises: 2c569d06001c
Create Date: 2026-07-09 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'ix_aul_user_created'
down_revision = '2c569d06001c'
branch_labels = None
depends_on = None


def upgrade():
    # Composite index for token-history queries that filter by (user_id, created_at >= ...)
    op.create_index(
        'ix_api_usage_logs_user_created',
        'api_usage_logs',
        ['user_id', 'created_at'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_api_usage_logs_user_created', table_name='api_usage_logs')
