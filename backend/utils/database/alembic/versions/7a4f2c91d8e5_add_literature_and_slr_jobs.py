"""add literature_items and slr_jobs

Revision ID: 7a4f2c91d8e5
Revises: 5d44264886f1
Create Date: 2026-05-21
"""

from alembic import op
import sqlalchemy as sa


revision = "7a4f2c91d8e5"
down_revision = "5d44264886f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "slr_jobs",
        sa.Column("id", sa.String(length=20), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("paper_id", sa.String(length=20), sa.ForeignKey("papers.id"), nullable=False),
        sa.Column(
            "conversation_id",
            sa.String(length=20),
            sa.ForeignKey("conversations.id"),
            nullable=True,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column("top_k", sa.Integer(), server_default="50"),
        sa.Column("per_source", sa.Integer(), server_default="60"),
        sa.Column("year_from", sa.Integer(), nullable=True),
        sa.Column("ai_summarize", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("ai_model", sa.String(length=40), server_default="V-OPUS"),
        sa.Column("status", sa.String(length=20), server_default="queued"),
        sa.Column("stage", sa.String(length=40), server_default=""),
        sa.Column("progress", sa.Integer(), server_default="0"),
        sa.Column("progress_message", sa.Text(), server_default=""),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), server_default=""),
        sa.Column("queued_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_slr_jobs_paper_id", "slr_jobs", ["paper_id"])
    op.create_index("ix_slr_jobs_user_id", "slr_jobs", ["user_id"])
    op.create_index("ix_slr_jobs_status", "slr_jobs", ["status"])

    op.create_table(
        "literature_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("paper_id", sa.String(length=20), sa.ForeignKey("papers.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_kind", sa.String(length=20), server_default="slr"),
        sa.Column("source", sa.String(length=40), server_default=""),
        sa.Column("title", sa.Text(), server_default=""),
        sa.Column("authors", sa.JSON(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("venue", sa.Text(), server_default=""),
        sa.Column("publisher", sa.Text(), server_default=""),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("url", sa.Text(), server_default=""),
        sa.Column("abstract", sa.Text(), server_default=""),
        sa.Column("summary", sa.Text(), server_default=""),
        sa.Column("citations", sa.Integer(), nullable=True),
        sa.Column("score_total", sa.Float(), nullable=True),
        sa.Column("score_breakdown", sa.JSON(), nullable=True),
        sa.Column("must_read", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("is_relevant", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("pinned", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("paper_files.id"), nullable=True),
        sa.Column("slr_job_id", sa.String(length=20), sa.ForeignKey("slr_jobs.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_literature_items_paper_id", "literature_items", ["paper_id"])
    op.create_index("ix_literature_items_doi", "literature_items", ["doi"])
    op.create_index("ix_literature_items_slr_job_id", "literature_items", ["slr_job_id"])


def downgrade():
    op.drop_index("ix_literature_items_slr_job_id", table_name="literature_items")
    op.drop_index("ix_literature_items_doi", table_name="literature_items")
    op.drop_index("ix_literature_items_paper_id", table_name="literature_items")
    op.drop_table("literature_items")
    op.drop_index("ix_slr_jobs_status", table_name="slr_jobs")
    op.drop_index("ix_slr_jobs_user_id", table_name="slr_jobs")
    op.drop_index("ix_slr_jobs_paper_id", table_name="slr_jobs")
    op.drop_table("slr_jobs")
