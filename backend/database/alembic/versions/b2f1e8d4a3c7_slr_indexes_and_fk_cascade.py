"""slr indexes and fk cascade

Revision ID: b2f1e8d4a3c7
Revises: 7a4f2c91d8e5
Create Date: 2026-05-22

Adds:
- composite index ix_slr_jobs_status_queued_at on slr_jobs(status, queued_at)
- ON DELETE SET NULL on literature_items.slr_job_id FK
- server_default for JSON columns (sources/result/authors/score_breakdown)
- partial unique index uq_literature_paper_doi on (paper_id, doi) WHERE doi IS NOT NULL
"""
from alembic import op
import sqlalchemy as sa


revision = 'b2f1e8d4a3c7'
down_revision = '7a4f2c91d8e5'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Composite index on slr_jobs(status, queued_at)
    op.create_index(
        'ix_slr_jobs_status_queued_at', 'slr_jobs',
        ['status', 'queued_at'],
    )

    # 2. JSON server_defaults — use batch_alter_table for SQLite compat
    with op.batch_alter_table('slr_jobs') as batch_op:
        batch_op.alter_column(
            'sources',
            existing_type=sa.JSON(),
            server_default=sa.text("'[]'"),
            existing_nullable=True,
        )
        batch_op.alter_column(
            'result',
            existing_type=sa.JSON(),
            server_default=sa.text("'{}'"),
            existing_nullable=True,
        )

    # 3. literature_items: FK ondelete=SET NULL + JSON server_defaults
    with op.batch_alter_table('literature_items') as batch_op:
        batch_op.alter_column(
            'authors',
            existing_type=sa.JSON(),
            server_default=sa.text("'[]'"),
            existing_nullable=True,
        )
        batch_op.alter_column(
            'score_breakdown',
            existing_type=sa.JSON(),
            server_default=sa.text("'{}'"),
            existing_nullable=True,
        )
        batch_op.drop_constraint(
            'literature_items_slr_job_id_fkey', type_='foreignkey'
        )
        batch_op.create_foreign_key(
            'literature_items_slr_job_id_fkey',
            'slr_jobs', ['slr_job_id'], ['id'],
            ondelete='SET NULL',
        )

    # 4. Partial unique index on (paper_id, doi) WHERE doi IS NOT NULL
    op.create_index(
        'uq_literature_paper_doi', 'literature_items',
        ['paper_id', 'doi'],
        unique=True,
        postgresql_where=sa.text('doi IS NOT NULL'),
        sqlite_where=sa.text('doi IS NOT NULL'),
    )


def downgrade():
    op.drop_index('uq_literature_paper_doi', table_name='literature_items')

    with op.batch_alter_table('literature_items') as batch_op:
        batch_op.drop_constraint(
            'literature_items_slr_job_id_fkey', type_='foreignkey'
        )
        batch_op.create_foreign_key(
            'literature_items_slr_job_id_fkey',
            'slr_jobs', ['slr_job_id'], ['id'],
        )
        batch_op.alter_column(
            'score_breakdown',
            existing_type=sa.JSON(),
            server_default=None,
            existing_nullable=True,
        )
        batch_op.alter_column(
            'authors',
            existing_type=sa.JSON(),
            server_default=None,
            existing_nullable=True,
        )

    with op.batch_alter_table('slr_jobs') as batch_op:
        batch_op.alter_column(
            'result',
            existing_type=sa.JSON(),
            server_default=None,
            existing_nullable=True,
        )
        batch_op.alter_column(
            'sources',
            existing_type=sa.JSON(),
            server_default=None,
            existing_nullable=True,
        )

    op.drop_index('ix_slr_jobs_status_queued_at', table_name='slr_jobs')
