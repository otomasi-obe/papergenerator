"""add_cascade_constraints_and_missing_indexes

Revision ID: f0121a767d17
Revises: b2f1e8d4a3c7
Create Date: 2026-05-23 01:13:00.754300

CRITICAL FIX: Add ON DELETE CASCADE to all foreign keys and missing indexes.

This migration addresses critical database integrity issues:
1. Adds ON DELETE CASCADE to foreign keys (prevents orphaned records)
2. Adds missing indexes on foreign keys (improves query performance)

Without CASCADE at DB level, manual cascade deletion in application code
is error-prone and can leave orphaned records if transactions fail.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f0121a767d17"
down_revision: Union[str, None] = "b2f1e8d4a3c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── Add missing indexes on foreign keys ─────────────────────────────────

    # PaperImage.user_id - missing index
    op.create_index("ix_paper_images_user_id", "paper_images", ["user_id"])

    # ApiUsageLog.user_id - missing index
    op.create_index("ix_api_usage_logs_user_id", "api_usage_logs", ["user_id"])

    # Conversation.user_id - missing index
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])

    # ChatMessage.conversation_id - missing index
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])

    # AiJob.user_id - missing index
    op.create_index("ix_ai_jobs_user_id", "ai_jobs", ["user_id"])

    # ─── Add CASCADE constraints to foreign keys ─────────────────────────────
    # We need to drop and recreate FKs with ondelete='CASCADE'
    # Using batch_alter_table for SQLite compatibility

    # 1. papers.user_id → users.id (CASCADE)
    with op.batch_alter_table("papers") as batch_op:
        batch_op.drop_constraint("papers_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "papers_user_id_fkey", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # 2. paper_images.paper_id → papers.id (CASCADE)
    with op.batch_alter_table("paper_images") as batch_op:
        batch_op.drop_constraint("paper_images_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "paper_images_paper_id_fkey", "papers", ["paper_id"], ["id"], ondelete="CASCADE"
        )

    # 3. paper_images.user_id → users.id (CASCADE)
    with op.batch_alter_table("paper_images") as batch_op:
        batch_op.drop_constraint("paper_images_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "paper_images_user_id_fkey", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # 4. paper_files.paper_id → papers.id (CASCADE)
    with op.batch_alter_table("paper_files") as batch_op:
        batch_op.drop_constraint("paper_files_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "paper_files_paper_id_fkey", "papers", ["paper_id"], ["id"], ondelete="CASCADE"
        )

    # 5. paper_files.user_id → users.id (CASCADE)
    with op.batch_alter_table("paper_files") as batch_op:
        batch_op.drop_constraint("paper_files_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "paper_files_user_id_fkey", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # 6. conversations.user_id → users.id (CASCADE)
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_constraint("conversations_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "conversations_user_id_fkey", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # 7. conversations.paper_id → papers.id (CASCADE)
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_constraint("conversations_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "conversations_paper_id_fkey", "papers", ["paper_id"], ["id"], ondelete="CASCADE"
        )

    # 8. chat_messages.conversation_id → conversations.id (CASCADE)
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_constraint("chat_messages_conversation_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chat_messages_conversation_id_fkey",
            "conversations",
            ["conversation_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # 9. project_memory.paper_id → papers.id (CASCADE)
    with op.batch_alter_table("project_memory") as batch_op:
        batch_op.drop_constraint("project_memory_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "project_memory_paper_id_fkey", "papers", ["paper_id"], ["id"], ondelete="CASCADE"
        )

    # 10. project_memory.user_id → users.id (CASCADE)
    with op.batch_alter_table("project_memory") as batch_op:
        batch_op.drop_constraint("project_memory_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "project_memory_user_id_fkey", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # Note: project_memory.conversation_id already has CASCADE (line 236 in models.py)

    # 11. ai_jobs.user_id → users.id (CASCADE)
    with op.batch_alter_table("ai_jobs") as batch_op:
        batch_op.drop_constraint("ai_jobs_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "ai_jobs_user_id_fkey", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # 12. ai_jobs.paper_id → papers.id (SET NULL - jobs should survive paper deletion for audit)
    with op.batch_alter_table("ai_jobs") as batch_op:
        batch_op.drop_constraint("ai_jobs_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "ai_jobs_paper_id_fkey", "papers", ["paper_id"], ["id"], ondelete="SET NULL"
        )

    # 13. literature_items.paper_id → papers.id (CASCADE)
    with op.batch_alter_table("literature_items") as batch_op:
        batch_op.drop_constraint("literature_items_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "literature_items_paper_id_fkey", "papers", ["paper_id"], ["id"], ondelete="CASCADE"
        )

    # 14. literature_items.user_id → users.id (CASCADE)
    with op.batch_alter_table("literature_items") as batch_op:
        batch_op.drop_constraint("literature_items_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "literature_items_user_id_fkey", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # 15. literature_items.file_id → paper_files.id (SET NULL)
    with op.batch_alter_table("literature_items") as batch_op:
        batch_op.drop_constraint("literature_items_file_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "literature_items_file_id_fkey", "paper_files", ["file_id"], ["id"], ondelete="SET NULL"
        )

    # Note: literature_items.slr_job_id already has SET NULL (migration b2f1e8d4a3c7)

    # 16. slr_jobs.user_id → users.id (CASCADE)
    with op.batch_alter_table("slr_jobs") as batch_op:
        batch_op.drop_constraint("slr_jobs_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "slr_jobs_user_id_fkey", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # 17. slr_jobs.paper_id → papers.id (CASCADE)
    with op.batch_alter_table("slr_jobs") as batch_op:
        batch_op.drop_constraint("slr_jobs_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "slr_jobs_paper_id_fkey", "papers", ["paper_id"], ["id"], ondelete="CASCADE"
        )

    # 18. slr_jobs.conversation_id → conversations.id (SET NULL)
    with op.batch_alter_table("slr_jobs") as batch_op:
        batch_op.drop_constraint("slr_jobs_conversation_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "slr_jobs_conversation_id_fkey",
            "conversations",
            ["conversation_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 19. image_gen_jobs.user_id → users.id (CASCADE)
    with op.batch_alter_table("image_gen_jobs") as batch_op:
        batch_op.drop_constraint("image_gen_jobs_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "image_gen_jobs_user_id_fkey", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # 20. image_gen_jobs.paper_id → papers.id (CASCADE)
    with op.batch_alter_table("image_gen_jobs") as batch_op:
        batch_op.drop_constraint("image_gen_jobs_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "image_gen_jobs_paper_id_fkey", "papers", ["paper_id"], ["id"], ondelete="CASCADE"
        )

    # 21. image_gen_jobs.image_id → paper_images.id (SET NULL)
    with op.batch_alter_table("image_gen_jobs") as batch_op:
        batch_op.drop_constraint("image_gen_jobs_image_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "image_gen_jobs_image_id_fkey",
            "paper_images",
            ["image_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    # ─── Remove CASCADE constraints (revert to no action) ───────────────────

    # Reverse order of upgrade

    with op.batch_alter_table("image_gen_jobs") as batch_op:
        batch_op.drop_constraint("image_gen_jobs_image_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "image_gen_jobs_image_id_fkey", "paper_images", ["image_id"], ["id"]
        )

    with op.batch_alter_table("image_gen_jobs") as batch_op:
        batch_op.drop_constraint("image_gen_jobs_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("image_gen_jobs_paper_id_fkey", "papers", ["paper_id"], ["id"])

    with op.batch_alter_table("image_gen_jobs") as batch_op:
        batch_op.drop_constraint("image_gen_jobs_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("image_gen_jobs_user_id_fkey", "users", ["user_id"], ["id"])

    with op.batch_alter_table("slr_jobs") as batch_op:
        batch_op.drop_constraint("slr_jobs_conversation_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "slr_jobs_conversation_id_fkey", "conversations", ["conversation_id"], ["id"]
        )

    with op.batch_alter_table("slr_jobs") as batch_op:
        batch_op.drop_constraint("slr_jobs_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("slr_jobs_paper_id_fkey", "papers", ["paper_id"], ["id"])

    with op.batch_alter_table("slr_jobs") as batch_op:
        batch_op.drop_constraint("slr_jobs_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("slr_jobs_user_id_fkey", "users", ["user_id"], ["id"])

    with op.batch_alter_table("literature_items") as batch_op:
        batch_op.drop_constraint("literature_items_file_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "literature_items_file_id_fkey", "paper_files", ["file_id"], ["id"]
        )

    with op.batch_alter_table("literature_items") as batch_op:
        batch_op.drop_constraint("literature_items_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("literature_items_user_id_fkey", "users", ["user_id"], ["id"])

    with op.batch_alter_table("literature_items") as batch_op:
        batch_op.drop_constraint("literature_items_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "literature_items_paper_id_fkey", "papers", ["paper_id"], ["id"]
        )

    with op.batch_alter_table("ai_jobs") as batch_op:
        batch_op.drop_constraint("ai_jobs_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("ai_jobs_paper_id_fkey", "papers", ["paper_id"], ["id"])

    with op.batch_alter_table("ai_jobs") as batch_op:
        batch_op.drop_constraint("ai_jobs_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("ai_jobs_user_id_fkey", "users", ["user_id"], ["id"])

    with op.batch_alter_table("project_memory") as batch_op:
        batch_op.drop_constraint("project_memory_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("project_memory_user_id_fkey", "users", ["user_id"], ["id"])

    with op.batch_alter_table("project_memory") as batch_op:
        batch_op.drop_constraint("project_memory_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("project_memory_paper_id_fkey", "papers", ["paper_id"], ["id"])

    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_constraint("chat_messages_conversation_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chat_messages_conversation_id_fkey", "conversations", ["conversation_id"], ["id"]
        )

    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_constraint("conversations_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("conversations_paper_id_fkey", "papers", ["paper_id"], ["id"])

    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_constraint("conversations_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("conversations_user_id_fkey", "users", ["user_id"], ["id"])

    with op.batch_alter_table("paper_files") as batch_op:
        batch_op.drop_constraint("paper_files_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("paper_files_user_id_fkey", "users", ["user_id"], ["id"])

    with op.batch_alter_table("paper_files") as batch_op:
        batch_op.drop_constraint("paper_files_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("paper_files_paper_id_fkey", "papers", ["paper_id"], ["id"])

    with op.batch_alter_table("paper_images") as batch_op:
        batch_op.drop_constraint("paper_images_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("paper_images_user_id_fkey", "users", ["user_id"], ["id"])

    with op.batch_alter_table("paper_images") as batch_op:
        batch_op.drop_constraint("paper_images_paper_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("paper_images_paper_id_fkey", "papers", ["paper_id"], ["id"])

    with op.batch_alter_table("papers") as batch_op:
        batch_op.drop_constraint("papers_user_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key("papers_user_id_fkey", "users", ["user_id"], ["id"])

    # ─── Drop indexes ────────────────────────────────────────────────────────
    op.drop_index("ix_ai_jobs_user_id", table_name="ai_jobs")
    op.drop_index("ix_chat_messages_conversation_id", table_name="chat_messages")
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_index("ix_api_usage_logs_user_id", table_name="api_usage_logs")
    op.drop_index("ix_paper_images_user_id", table_name="paper_images")
