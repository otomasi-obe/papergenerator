"""chat-scoped memory + paused status

Revision ID: c3a9f7b2e154
Revises: b2f1e8d4a3c7
Create Date: 2026-05-22

Schema changes:
- project_memory: add `conversation_id VARCHAR(20)` with FK to conversations(id)
  ON DELETE CASCADE (nullable). NULL means paper-global memory; non-NULL means
  chat-scoped memory. Existing rows stay readable as global.
- Drop the old `uq_project_memory_paper_key` UNIQUE(paper_id, key) and replace
  with two partial unique indexes:
    * uq_pm_paper_key_global   WHERE conversation_id IS NULL
    * uq_pm_paper_conv_key     WHERE conversation_id IS NOT NULL
  Both Postgres and SQLite (>=3.8.0) support partial indexes.
- ai_jobs.status now documents `paused` as a valid value (no schema change).
"""
from alembic import op
import sqlalchemy as sa


revision = 'c3a9f7b2e154'
down_revision = 'b2f1e8d4a3c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add conversation_id column + FK + index using batch_alter_table for
    #    SQLite compatibility (no-op on Postgres beyond the wrapper).
    with op.batch_alter_table('project_memory') as batch_op:
        batch_op.add_column(
            sa.Column('conversation_id', sa.String(length=20), nullable=True)
        )
        batch_op.create_foreign_key(
            'project_memory_conversation_id_fkey',
            'conversations',
            ['conversation_id'], ['id'],
            ondelete='CASCADE',
        )
        batch_op.create_index(
            'ix_project_memory_conversation_id',
            ['conversation_id'],
        )
        # Drop the old unique constraint on (paper_id, key).
        batch_op.drop_constraint(
            'uq_project_memory_paper_key', type_='unique'
        )

    # 2. Two partial unique indexes covering each scope.
    op.create_index(
        'uq_pm_paper_key_global', 'project_memory',
        ['paper_id', 'key'],
        unique=True,
        postgresql_where=sa.text('conversation_id IS NULL'),
        sqlite_where=sa.text('conversation_id IS NULL'),
    )
    op.create_index(
        'uq_pm_paper_conv_key', 'project_memory',
        ['paper_id', 'conversation_id', 'key'],
        unique=True,
        postgresql_where=sa.text('conversation_id IS NOT NULL'),
        sqlite_where=sa.text('conversation_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_pm_paper_conv_key', table_name='project_memory')
    op.drop_index('uq_pm_paper_key_global', table_name='project_memory')

    with op.batch_alter_table('project_memory') as batch_op:
        batch_op.create_unique_constraint(
            'uq_project_memory_paper_key', ['paper_id', 'key']
        )
        batch_op.drop_index('ix_project_memory_conversation_id')
        batch_op.drop_constraint(
            'project_memory_conversation_id_fkey', type_='foreignkey'
        )
        batch_op.drop_column('conversation_id')
