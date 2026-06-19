"""add title_norm column + unique index for literature dedup

Menambahkan kolom title_norm (normalized title untuk dedup) pada tabel
literature_items, serta partial unique index uq_literature_title_norm
pada (paper_id, title_norm) untuk cegah duplikat judul dalam satu paper.

Revision ID: add_title_norm_dedup_001
Revises: is_checked_001
Create Date: 2026-06-18

"""
from alembic import op
import sqlalchemy as sa
import re

# revision identifiers, used by Alembic.
revision = "add_title_norm_dedup_001"
down_revision = "is_checked_001"
branch_labels = None
depends_on = None


def _normalize_title(title: str) -> str:
    """Normalize title: lowercase, strip non-alphanumeric. Max 500 chars."""
    if not title:
        return ""
    return re.sub(r'[^a-z0-9]+', '', title.lower())[:500]


def upgrade():
    bind = op.get_bind()

    # 1. Add column (nullable, default '' for new rows)
    op.add_column(
        "literature_items",
        sa.Column("title_norm", sa.Text(), nullable=True, server_default=""),
    )

    # 2. Backfill title_norm for existing rows
    #    Batch-update rows where title is non-empty
    if bind.dialect.name == "postgresql":
        op.execute(
            "UPDATE literature_items "
            "SET title_norm = LOWER(REGEXP_REPLACE(COALESCE(title, ''), '[^a-z0-9]', '', 'g')) "
            "WHERE title IS NOT NULL AND title != ''"
        )
        # Truncate to 500 chars post-backfill
        op.execute(
            "UPDATE literature_items "
            "SET title_norm = LEFT(title_norm, 500) "
            "WHERE LENGTH(title_norm) > 500"
        )
        # 2b. Clean duplicates before creating unique index.
        #     Keep the row with most data (non-empty fields count)
        #     per (paper_id, title_norm) group. Prefer pinned rows,
        #     then rows with more non-empty fields, then highest id.
        op.execute(sa.text("""
            DELETE FROM literature_items
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY paper_id, title_norm
                               ORDER BY
                                   pinned DESC,
                                   (CASE WHEN abstract IS NOT NULL AND abstract != '' THEN 1 ELSE 0 END) +
                                   (CASE WHEN authors IS NOT NULL THEN 1 ELSE 0 END) +
                                   (CASE WHEN doi IS NOT NULL THEN 1 ELSE 0 END) +
                                   (CASE WHEN year IS NOT NULL THEN 1 ELSE 0 END) +
                                   (CASE WHEN summary IS NOT NULL AND summary != '' THEN 1 ELSE 0 END) DESC,
                                   id DESC
                           ) AS rn
                    FROM literature_items
                    WHERE title_norm IS NOT NULL AND title_norm != ''
                ) sub
                WHERE rn > 1
            )
        """))
    else:
        # SQLite — use Python-side backfill
        conn = bind.connect()
        rows = conn.execute(
            sa.text("SELECT id, title FROM literature_items WHERE title IS NOT NULL AND title != ''")
        ).fetchall()
        for row_id, title in rows:
            norm = _normalize_title(title)
            if norm:
                conn.execute(
                    sa.text("UPDATE literature_items SET title_norm = :norm WHERE id = :id"),
                    {"norm": norm, "id": row_id},
                )
        conn.commit()

    # 3. Add partial unique index
    op.create_index(
        "uq_literature_title_norm",
        "literature_items",
        ["paper_id", "title_norm"],
        unique=True,
        postgresql_where=sa.text("title_norm IS NOT NULL AND title_norm != ''"),
        sqlite_where=sa.text("title_norm IS NOT NULL AND title_norm != ''"),
    )


def downgrade():
    op.drop_index("uq_literature_title_norm", table_name="literature_items")
    op.drop_column("literature_items", "title_norm")