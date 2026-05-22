-- ============================================================================
-- Rollback: Revert CASCADE DELETE/SET NULL to NO ACTION
-- ============================================================================
-- Date: 2026-05-22
-- Purpose: Rollback fix_cascade_constraints.sql if needed
-- Warning: This removes database-level referential integrity protections
-- ============================================================================

BEGIN;

-- Verify we're on the correct database
DO $$
BEGIN
    IF current_database() != 'papergenerator' THEN
        RAISE EXCEPTION 'Wrong database! Expected papergenerator, got %', current_database();
    END IF;
END $$;

-- ============================================================================
-- REVERT ALL CONSTRAINTS TO NO ACTION
-- ============================================================================

-- papers
ALTER TABLE papers 
    DROP CONSTRAINT papers_user_id_fkey,
    ADD CONSTRAINT papers_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);

-- paper_images
ALTER TABLE paper_images 
    DROP CONSTRAINT paper_images_paper_id_fkey,
    ADD CONSTRAINT paper_images_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id);

ALTER TABLE paper_images 
    DROP CONSTRAINT paper_images_user_id_fkey,
    ADD CONSTRAINT paper_images_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);

-- paper_files
ALTER TABLE paper_files 
    DROP CONSTRAINT paper_files_paper_id_fkey,
    ADD CONSTRAINT paper_files_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id);

ALTER TABLE paper_files 
    DROP CONSTRAINT paper_files_user_id_fkey,
    ADD CONSTRAINT paper_files_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);

-- conversations
ALTER TABLE conversations 
    DROP CONSTRAINT conversations_paper_id_fkey,
    ADD CONSTRAINT conversations_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id);

ALTER TABLE conversations 
    DROP CONSTRAINT conversations_user_id_fkey,
    ADD CONSTRAINT conversations_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);

-- chat_messages
ALTER TABLE chat_messages 
    DROP CONSTRAINT chat_messages_conversation_id_fkey,
    ADD CONSTRAINT chat_messages_conversation_id_fkey 
        FOREIGN KEY (conversation_id) REFERENCES conversations(id);

-- project_memory
ALTER TABLE project_memory 
    DROP CONSTRAINT project_memory_paper_id_fkey,
    ADD CONSTRAINT project_memory_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id);

-- Keep project_memory.conversation_id as CASCADE (was already correct)
-- Keep project_memory.user_id reverted
ALTER TABLE project_memory 
    DROP CONSTRAINT project_memory_user_id_fkey,
    ADD CONSTRAINT project_memory_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);

-- ai_jobs
ALTER TABLE ai_jobs 
    DROP CONSTRAINT ai_jobs_paper_id_fkey,
    ADD CONSTRAINT ai_jobs_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id);

ALTER TABLE ai_jobs 
    DROP CONSTRAINT ai_jobs_user_id_fkey,
    ADD CONSTRAINT ai_jobs_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);

-- slr_jobs
ALTER TABLE slr_jobs 
    DROP CONSTRAINT slr_jobs_paper_id_fkey,
    ADD CONSTRAINT slr_jobs_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id);

ALTER TABLE slr_jobs 
    DROP CONSTRAINT slr_jobs_user_id_fkey,
    ADD CONSTRAINT slr_jobs_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);

ALTER TABLE slr_jobs 
    DROP CONSTRAINT slr_jobs_conversation_id_fkey,
    ADD CONSTRAINT slr_jobs_conversation_id_fkey 
        FOREIGN KEY (conversation_id) REFERENCES conversations(id);

-- image_gen_jobs
ALTER TABLE image_gen_jobs 
    DROP CONSTRAINT image_gen_jobs_paper_id_fkey,
    ADD CONSTRAINT image_gen_jobs_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id);

ALTER TABLE image_gen_jobs 
    DROP CONSTRAINT image_gen_jobs_user_id_fkey,
    ADD CONSTRAINT image_gen_jobs_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);

ALTER TABLE image_gen_jobs 
    DROP CONSTRAINT image_gen_jobs_image_id_fkey,
    ADD CONSTRAINT image_gen_jobs_image_id_fkey 
        FOREIGN KEY (image_id) REFERENCES paper_images(id);

-- literature_items
ALTER TABLE literature_items 
    DROP CONSTRAINT literature_items_paper_id_fkey,
    ADD CONSTRAINT literature_items_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id);

ALTER TABLE literature_items 
    DROP CONSTRAINT literature_items_user_id_fkey,
    ADD CONSTRAINT literature_items_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);

ALTER TABLE literature_items 
    DROP CONSTRAINT literature_items_file_id_fkey,
    ADD CONSTRAINT literature_items_file_id_fkey 
        FOREIGN KEY (file_id) REFERENCES paper_files(id);

-- Keep literature_items.slr_job_id as SET NULL (was already correct)

-- api_usage_logs
ALTER TABLE api_usage_logs 
    DROP CONSTRAINT api_usage_logs_user_id_fkey,
    ADD CONSTRAINT api_usage_logs_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id);

COMMIT;

RAISE NOTICE 'Rollback complete. All constraints reverted to NO ACTION.';
