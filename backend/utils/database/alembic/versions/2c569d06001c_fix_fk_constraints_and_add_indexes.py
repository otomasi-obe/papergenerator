"""fix_fk_constraints_and_add_indexes

Revision ID: 2c569d06001c
Revises: add_title_norm_dedup_001
Create Date: 2026-06-25

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '2c569d06001c'
down_revision: Union[str, None] = 'add_title_norm_dedup_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fix FK: ai_jobs.paper_id → ON DELETE SET NULL (was CASCADE)
    op.drop_constraint('ai_jobs_paper_id_fkey', 'ai_jobs', type_='foreignkey')
    op.create_foreign_key(
        'ai_jobs_paper_id_fkey', 'ai_jobs', 'papers',
        ['paper_id'], ['id'], ondelete='SET NULL'
    )

    # Fix FK: api_usage_logs.user_id → ON DELETE SET NULL (was CASCADE)
    op.drop_constraint('api_usage_logs_user_id_fkey', 'api_usage_logs', type_='foreignkey')
    op.create_foreign_key(
        'api_usage_logs_user_id_fkey', 'api_usage_logs', 'users',
        ['user_id'], ['id'], ondelete='SET NULL'
    )

    # Fix FK: chat_drafts.paper_id → ON DELETE CASCADE (was NO ACTION)
    op.drop_constraint('chat_drafts_paper_id_fkey', 'chat_drafts', type_='foreignkey')
    op.create_foreign_key(
        'chat_drafts_paper_id_fkey', 'chat_drafts', 'papers',
        ['paper_id'], ['id'], ondelete='CASCADE'
    )

    # Fix FK: chat_drafts.user_id → ON DELETE CASCADE (was NO ACTION)
    op.drop_constraint('chat_drafts_user_id_fkey', 'chat_drafts', type_='foreignkey')
    op.create_foreign_key(
        'chat_drafts_user_id_fkey', 'chat_drafts', 'users',
        ['user_id'], ['id'], ondelete='CASCADE'
    )

    # Fix FK: slr_jobs.conversation_id → ON DELETE SET NULL (was CASCADE)
    op.drop_constraint('slr_jobs_conversation_id_fkey', 'slr_jobs', type_='foreignkey')
    op.create_foreign_key(
        'slr_jobs_conversation_id_fkey', 'slr_jobs', 'conversations',
        ['conversation_id'], ['id'], ondelete='SET NULL'
    )

    # Fix FK: user_states.user_id → ON DELETE CASCADE (was NO ACTION)
    op.drop_constraint('user_states_user_id_fkey', 'user_states', type_='foreignkey')
    op.create_foreign_key(
        'user_states_user_id_fkey', 'user_states', 'users',
        ['user_id'], ['id'], ondelete='CASCADE'
    )

    # Add composite index for ai_jobs filtering
    op.create_index(
        'ix_ai_jobs_user_paper_kind', 'ai_jobs',
        ['user_id', 'paper_id', 'kind'], unique=False
    )

    # Add composite index for image_gen_jobs polling
    op.create_index(
        'ix_image_gen_jobs_status_created_at', 'image_gen_jobs',
        ['status', 'created_at'], unique=False
    )


def downgrade() -> None:
    # Drop new indexes
    op.drop_index('ix_image_gen_jobs_status_created_at', table_name='image_gen_jobs')
    op.drop_index('ix_ai_jobs_user_paper_kind', table_name='ai_jobs')

    # Revert FK: user_states.user_id
    op.drop_constraint('user_states_user_id_fkey', 'user_states', type_='foreignkey')
    op.create_foreign_key(
        'user_states_user_id_fkey', 'user_states', 'users',
        ['user_id'], ['id']
    )

    # Revert FK: slr_jobs.conversation_id
    op.drop_constraint('slr_jobs_conversation_id_fkey', 'slr_jobs', type_='foreignkey')
    op.create_foreign_key(
        'slr_jobs_conversation_id_fkey', 'slr_jobs', 'conversations',
        ['conversation_id'], ['id'], ondelete='CASCADE'
    )

    # Revert FK: chat_drafts.user_id
    op.drop_constraint('chat_drafts_user_id_fkey', 'chat_drafts', type_='foreignkey')
    op.create_foreign_key(
        'chat_drafts_user_id_fkey', 'chat_drafts', 'users',
        ['user_id'], ['id']
    )

    # Revert FK: chat_drafts.paper_id
    op.drop_constraint('chat_drafts_paper_id_fkey', 'chat_drafts', type_='foreignkey')
    op.create_foreign_key(
        'chat_drafts_paper_id_fkey', 'chat_drafts', 'papers',
        ['paper_id'], ['id']
    )

    # Revert FK: api_usage_logs.user_id
    op.drop_constraint('api_usage_logs_user_id_fkey', 'api_usage_logs', type_='foreignkey')
    op.create_foreign_key(
        'api_usage_logs_user_id_fkey', 'api_usage_logs', 'users',
        ['user_id'], ['id'], ondelete='CASCADE'
    )

    # Revert FK: ai_jobs.paper_id
    op.drop_constraint('ai_jobs_paper_id_fkey', 'ai_jobs', type_='foreignkey')
    op.create_foreign_key(
        'ai_jobs_paper_id_fkey', 'ai_jobs', 'papers',
        ['paper_id'], ['id'], ondelete='CASCADE'
    )
