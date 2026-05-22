"""add operation locking to papers

Revision ID: b1de57988b40
Revises: c3a9f7b2e154
Create Date: 2026-05-22

Schema changes:
- papers: add `active_operation VARCHAR(50)` (nullable) to track current operation
- papers: add `active_operation_job_id VARCHAR(50)` (nullable) to track job ID
- papers: add `active_operation_started_at DATETIME` (nullable) to track start time
"""
from alembic import op
import sqlalchemy as sa


revision = 'b1de57988b40'
down_revision = 'c3a9f7b2e154'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('papers') as batch_op:
        batch_op.add_column(
            sa.Column('active_operation', sa.String(length=50), nullable=True)
        )
        batch_op.add_column(
            sa.Column('active_operation_job_id', sa.String(length=50), nullable=True)
        )
        batch_op.add_column(
            sa.Column('active_operation_started_at', sa.DateTime(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('papers') as batch_op:
        batch_op.drop_column('active_operation_started_at')
        batch_op.drop_column('active_operation_job_id')
        batch_op.drop_column('active_operation')
