"""Fix schema drift: index definitions and column types to match models.

- Recreate uq_pm_paper_conv_key with correct column order + partial WHERE
- Recreate uq_literature_paper_doi with partial WHERE
- literature_items.source: text → varchar(40) is NOT done (keep text, model updated)
- users.refresh_token_hash: already exists in DB, model now synced

Revision ID: fix_schema_drift_2026
Revises: merge_all_heads
Create Date: 2026-07-04
"""

from alembic import op
import sqlalchemy as sa

revision = "fix_schema_drift_2026"
down_revision = "merge_all_heads"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Fix project_memory index: wrong column order + missing partial WHERE
    op.execute("DROP INDEX IF EXISTS uq_pm_paper_conv_key")
    op.execute("""
        CREATE UNIQUE INDEX uq_pm_paper_conv_key
        ON project_memory (paper_id, conversation_id, key)
        WHERE conversation_id IS NOT NULL
    """)

    # 2. Fix literature_items DOI index: missing partial WHERE
    op.execute("DROP INDEX IF EXISTS uq_literature_paper_doi")
    op.execute("""
        CREATE UNIQUE INDEX uq_literature_paper_doi
        ON literature_items (paper_id, doi)
        WHERE doi IS NOT NULL
    """)


def downgrade():
    # Revert to old (non-partial) indexes
    op.execute("DROP INDEX IF EXISTS uq_pm_paper_conv_key")
    op.execute("""
        CREATE UNIQUE INDEX uq_pm_paper_conv_key
        ON project_memory (paper_id, key, conversation_id)
    """)

    op.execute("DROP INDEX IF EXISTS uq_literature_paper_doi")
    op.execute("""
        CREATE UNIQUE INDEX uq_literature_paper_doi
        ON literature_items (paper_id, doi)
    """)
