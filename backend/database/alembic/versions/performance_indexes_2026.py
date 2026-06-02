"""add performance indexes

Revision ID: perf_idx_2026
Revises: b2f1e8d4a3c7
Create Date: 2026-05-26 14:42:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'perf_idx_2026'
down_revision = 'b2f1e8d4a3c7'
branch_labels = None
depends_on = None


def upgrade():
    # Papers table - critical missing indexes
    op.create_index('ix_papers_user_id', 'papers', ['user_id'], unique=False)
    op.create_index('ix_papers_updated_at', 'papers', ['updated_at'], unique=False)
    op.create_index('ix_papers_user_updated', 'papers', ['user_id', 'updated_at'], unique=False)
    op.create_index('ix_papers_created_at', 'papers', ['created_at'], unique=False)
    
    # Users table - improve query performance
    op.create_index('ix_users_created_at', 'users', ['created_at'], unique=False)
    op.create_index('ix_users_role', 'users', ['role'], unique=False)
    
    # AiJob table - improve status queries
    op.create_index('ix_ai_jobs_user_status', 'ai_jobs', ['user_id', 'status'], unique=False)
    op.create_index('ix_ai_jobs_started_at', 'ai_jobs', ['started_at'], unique=False)
    
    # Conversations table - improve lookups
    op.create_index('ix_conversations_user_id', 'conversations', ['user_id'], unique=False)
    op.create_index('ix_conversations_paper_id', 'conversations', ['paper_id'], unique=False)
    op.create_index('ix_conversations_updated_at', 'conversations', ['updated_at'], unique=False)
    
    # ChatMessage table - improve conversation queries
    op.create_index('ix_chat_messages_conversation_id', 'chat_messages', ['conversation_id'], unique=False)
    op.create_index('ix_chat_messages_created_at', 'chat_messages', ['created_at'], unique=False)
    
    # PaperImage table - improve paper lookups
    op.create_index('ix_paper_images_paper_id', 'paper_images', ['paper_id'], unique=False)
    op.create_index('ix_paper_images_user_id', 'paper_images', ['user_id'], unique=False)
    
    # ApiUsageLog table - improve analytics queries
    op.create_index('ix_api_usage_logs_user_id', 'api_usage_logs', ['user_id'], unique=False)
    op.create_index('ix_api_usage_logs_created_at', 'api_usage_logs', ['created_at'], unique=False)
    op.create_index('ix_api_usage_logs_endpoint', 'api_usage_logs', ['endpoint'], unique=False)
    
    # ProjectMemory table - already has paper_id index, add composite
    op.create_index('ix_project_memory_paper_conv', 'project_memory', ['paper_id', 'conversation_id'], unique=False)
    
    # ImageGenJob table - improve status queries
    op.create_index('ix_image_gen_jobs_user_id', 'image_gen_jobs', ['user_id'], unique=False)
    op.create_index('ix_image_gen_jobs_status', 'image_gen_jobs', ['status'], unique=False)
    op.create_index('ix_image_gen_jobs_created_at', 'image_gen_jobs', ['created_at'], unique=False)


def downgrade():
    # Papers
    op.drop_index('ix_papers_user_updated', table_name='papers')
    op.drop_index('ix_papers_updated_at', table_name='papers')
    op.drop_index('ix_papers_user_id', table_name='papers')
    op.drop_index('ix_papers_created_at', table_name='papers')
    
    # Users
    op.drop_index('ix_users_created_at', table_name='users')
    op.drop_index('ix_users_role', table_name='users')
    
    # AiJob
    op.drop_index('ix_ai_jobs_user_status', table_name='ai_jobs')
    op.drop_index('ix_ai_jobs_started_at', table_name='ai_jobs')
    
    # Conversations
    op.drop_index('ix_conversations_user_id', table_name='conversations')
    op.drop_index('ix_conversations_paper_id', table_name='conversations')
    op.drop_index('ix_conversations_updated_at', table_name='conversations')
    
    # ChatMessage
    op.drop_index('ix_chat_messages_conversation_id', table_name='chat_messages')
    op.drop_index('ix_chat_messages_created_at', table_name='chat_messages')
    
    # PaperImage
    op.drop_index('ix_paper_images_paper_id', table_name='paper_images')
    op.drop_index('ix_paper_images_user_id', table_name='paper_images')
    
    # ApiUsageLog
    op.drop_index('ix_api_usage_logs_user_id', table_name='api_usage_logs')
    op.drop_index('ix_api_usage_logs_created_at', table_name='api_usage_logs')
    op.drop_index('ix_api_usage_logs_endpoint', table_name='api_usage_logs')
    
    # ProjectMemory
    op.drop_index('ix_project_memory_paper_conv', table_name='project_memory')
    
    # ImageGenJob
    op.drop_index('ix_image_gen_jobs_user_id', table_name='image_gen_jobs')
    op.drop_index('ix_image_gen_jobs_status', table_name='image_gen_jobs')
    op.drop_index('ix_image_gen_jobs_created_at', table_name='image_gen_jobs')
