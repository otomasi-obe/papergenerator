"""convert JSON columns to JSONB and meta_authors Text->JSONB

Mengubah kolom yang sebelumnya pakai plain JSON menjadi JSONB di PostgreSQL,
serta mengubah paper_files.meta_authors dari Text (berisi string JSON array)
menjadi JSONB.

Revision ID: jsonb_migration_001
Revises: gap_riset_001
Create Date: 2026-06-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "jsonb_migration_001"
down_revision = "gap_riset_001"
branch_labels = None
depends_on = None


# (table, column) untuk kolom JSON -> JSONB
_JSON_COLS = [
    ("chat_messages", "tool_calls"),
    ("ai_jobs", "result"),
    ("literature_items", "authors"),
    ("literature_items", "score_breakdown"),
    ("chat_drafts", "tags"),
    ("slr_jobs", "sources"),
    ("slr_jobs", "result"),
]


def upgrade():
    bind = op.get_bind()
    # Migrasi JSONB hanya relevan untuk PostgreSQL. Pada SQLite, JSON dan JSONB
    # keduanya dipetakan ke tipe yang sama, jadi tidak perlu ALTER.
    if bind.dialect.name != "postgresql":
        return

    for table, col in _JSON_COLS:
        op.execute(
            f'ALTER TABLE {table} '
            f'ALTER COLUMN {col} TYPE jsonb USING {col}::jsonb'
        )

    # paper_files.meta_authors: Text (string JSON array) -> JSONB.
    # Tangani nilai kosong / NULL agar menjadi array kosong yang valid.
    op.execute("ALTER TABLE paper_files ALTER COLUMN meta_authors DROP DEFAULT")
    op.execute(
        "ALTER TABLE paper_files "
        "ALTER COLUMN meta_authors TYPE jsonb USING ("
        "CASE WHEN meta_authors = '' OR meta_authors IS NULL "
        "THEN '[]'::jsonb ELSE meta_authors::jsonb END)"
    )
    op.execute("ALTER TABLE paper_files ALTER COLUMN meta_authors SET DEFAULT '[]'::jsonb")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table, col in _JSON_COLS:
        op.execute(
            f'ALTER TABLE {table} '
            f'ALTER COLUMN {col} TYPE json USING {col}::json'
        )

    # meta_authors kembali ke Text (serialisasi JSON string), default "".
    op.execute("ALTER TABLE paper_files ALTER COLUMN meta_authors DROP DEFAULT")
    op.execute(
        "ALTER TABLE paper_files "
        "ALTER COLUMN meta_authors TYPE text USING meta_authors::text"
    )
    op.execute("ALTER TABLE paper_files ALTER COLUMN meta_authors SET DEFAULT ''")
