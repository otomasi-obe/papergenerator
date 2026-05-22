-- ============================================================================
-- Migration: Add CASCADE DELETE/SET NULL to Foreign Key Constraints
-- ============================================================================
-- Date: 2026-05-22
-- Purpose: Add proper CASCADE behaviors at database level to prevent orphaned
--          records when deletions bypass SQLAlchemy ORM
-- Risk: Medium - Requires ALTER TABLE with brief locks
-- Rollback: See rollback_cascade_constraints.sql
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
-- 1. PAPERS TABLE
-- ============================================================================

-- papers.user_id → CASCADE (delete papers when user deleted)
ALTER TABLE papers 
    DROP CONSTRAINT papers_user_id_fkey,
    ADD CONSTRAINT papers_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id) 
        ON DELETE CASCADE;

-- ============================================================================
-- 2. PAPER_IMAGES TABLE
-- ============================================================================

-- paper_images.paper_id → CASCADE (delete images when paper deleted)
ALTER TABLE paper_images 
    DROP CONSTRAINT paper_images_paper_id_fkey,
    ADD CONSTRAINT paper_images_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id) 
        ON DELETE CASCADE;

-- paper_images.user_id → CASCADE (delete images when user deleted)
ALTER TABLE paper_images 
    DROP CONSTRAINT paper_images_user_id_fkey,
    ADD CONSTRAINT paper_images_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id) 
        ON DELETE CASCADE;

-- ============================================================================
-- 3. PAPER_FILES TABLE
-- ============================================================================

-- paper_files.paper_id → CASCADE (delete files when paper deleted)
ALTER TABLE paper_files 
    DROP CONSTRAINT paper_files_paper_id_fkey,
    ADD CONSTRAINT paper_files_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id) 
        ON DELETE CASCADE;

-- paper_files.user_id → CASCADE (delete files when user deleted)
ALTER TABLE paper_files 
    DROP CONSTRAINT paper_files_user_id_fkey,
    ADD CONSTRAINT paper_files_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id) 
        ON DELETE CASCADE;

-- ============================================================================
-- 4. CONVERSATIONS TABLE
-- ============================================================================

-- conversations.paper_id → CASCADE (delete conversations when paper deleted)
ALTER TABLE conversations 
    DROP CONSTRAINT conversations_paper_id_fkey,
    ADD CONSTRAINT conversations_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id) 
        ON DELETE CASCADE;

-- conversations.user_id → CASCADE (delete conversations when user deleted)
ALTER TABLE conversations 
    DROP CONSTRAINT conversations_user_id_fkey,
    ADD CONSTRAINT conversations_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id) 
        ON DELETE CASCADE;

-- ============================================================================
-- 5. CHAT_MESSAGES TABLE
-- ============================================================================

-- chat_messages.conversation_id → CASCADE (delete messages when conversation deleted)
ALTER TABLE chat_messages 
    DROP CONSTRAINT chat_messages_conversation_id_fkey,
    ADD CONSTRAINT chat_messages_conversation_id_fkey 
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) 
        ON DELETE CASCADE;

-- ============================================================================
-- 6. PROJECT_MEMORY TABLE
-- ============================================================================

-- project_memory.paper_id → CASCADE (delete memory when paper deleted)
ALTER TABLE project_memory 
    DROP CONSTRAINT project_memory_paper_id_fkey,
    ADD CONSTRAINT project_memory_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id) 
        ON DELETE CASCADE;

-- project_memory.conversation_id → CASCADE (already correct, skip)
-- project_memory.user_id → CASCADE (delete memory when user deleted)
ALTER TABLE project_memory 
    DROP CONSTRAINT project_memory_user_id_fkey,
    ADD CONSTRAINT project_memory_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id) 
        ON DELETE CASCADE;

-- ============================================================================
-- 7. AI_JOBS TABLE
-- ============================================================================

-- ai_jobs.paper_id → SET NULL (keep job history even if paper deleted)
ALTER TABLE ai_jobs 
    DROP CONSTRAINT ai_jobs_paper_id_fkey,
    ADD CONSTRAINT ai_jobs_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id) 
        ON DELETE SET NULL;

-- ai_jobs.user_id → SET NULL (keep job history even if user deleted)
ALTER TABLE ai_jobs 
    DROP CONSTRAINT ai_jobs_user_id_fkey,
    ADD CONSTRAINT ai_jobs_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id) 
        ON DELETE SET NULL;

-- ============================================================================
-- 8. SLR_JOBS TABLE
-- ============================================================================

-- slr_jobs.paper_id → CASCADE (delete SLR jobs when paper deleted)
ALTER TABLE slr_jobs 
    DROP CONSTRAINT slr_jobs_paper_id_fkey,
    ADD CONSTRAINT slr_jobs_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id) 
        ON DELETE CASCADE;

-- slr_jobs.user_id → SET NULL (keep job history even if user deleted)
ALTER TABLE slr_jobs 
    DROP CONSTRAINT slr_jobs_user_id_fkey,
    ADD CONSTRAINT slr_jobs_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id) 
        ON DELETE SET NULL;

-- slr_jobs.conversation_id → SET NULL (keep job even if conversation deleted)
ALTER TABLE slr_jobs 
    DROP CONSTRAINT slr_jobs_conversation_id_fkey,
    ADD CONSTRAINT slr_jobs_conversation_id_fkey 
        FOREIGN KEY (conversation_id) REFERENCES conversations(id) 
        ON DELETE SET NULL;

-- ============================================================================
-- 9. IMAGE_GEN_JOBS TABLE
-- ============================================================================

-- image_gen_jobs.paper_id → CASCADE (delete image jobs when paper deleted)
ALTER TABLE image_gen_jobs 
    DROP CONSTRAINT image_gen_jobs_paper_id_fkey,
    ADD CONSTRAINT image_gen_jobs_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id) 
        ON DELETE CASCADE;

-- image_gen_jobs.user_id → SET NULL (keep job history even if user deleted)
ALTER TABLE image_gen_jobs 
    DROP CONSTRAINT image_gen_jobs_user_id_fkey,
    ADD CONSTRAINT image_gen_jobs_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id) 
        ON DELETE SET NULL;

-- image_gen_jobs.image_id → SET NULL (keep job even if image deleted)
ALTER TABLE image_gen_jobs 
    DROP CONSTRAINT image_gen_jobs_image_id_fkey,
    ADD CONSTRAINT image_gen_jobs_image_id_fkey 
        FOREIGN KEY (image_id) REFERENCES paper_images(id) 
        ON DELETE SET NULL;

-- ============================================================================
-- 10. LITERATURE_ITEMS TABLE
-- ============================================================================

-- literature_items.paper_id → CASCADE (delete literature when paper deleted)
ALTER TABLE literature_items 
    DROP CONSTRAINT literature_items_paper_id_fkey,
    ADD CONSTRAINT literature_items_paper_id_fkey 
        FOREIGN KEY (paper_id) REFERENCES papers(id) 
        ON DELETE CASCADE;

-- literature_items.user_id → CASCADE (delete literature when user deleted)
ALTER TABLE literature_items 
    DROP CONSTRAINT literature_items_user_id_fkey,
    ADD CONSTRAINT literature_items_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id) 
        ON DELETE CASCADE;

-- literature_items.file_id → SET NULL (keep literature item even if file deleted)
ALTER TABLE literature_items 
    DROP CONSTRAINT literature_items_file_id_fkey,
    ADD CONSTRAINT literature_items_file_id_fkey 
        FOREIGN KEY (file_id) REFERENCES paper_files(id) 
        ON DELETE SET NULL;

-- literature_items.slr_job_id → SET NULL (already correct, skip)

-- ============================================================================
-- 11. API_USAGE_LOGS TABLE
-- ============================================================================

-- api_usage_logs.user_id → SET NULL (keep logs for analytics even if user deleted)
ALTER TABLE api_usage_logs 
    DROP CONSTRAINT api_usage_logs_user_id_fkey,
    ADD CONSTRAINT api_usage_logs_user_id_fkey 
        FOREIGN KEY (user_id) REFERENCES users(id) 
        ON DELETE SET NULL;

-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Verify all constraints are now correct
DO $$
DECLARE
    cascade_count INTEGER;
    set_null_count INTEGER;
BEGIN
    -- Count CASCADE constraints
    SELECT COUNT(*) INTO cascade_count
    FROM information_schema.referential_constraints
    WHERE constraint_schema = 'public'
      AND delete_rule = 'CASCADE';
    
    -- Count SET NULL constraints
    SELECT COUNT(*) INTO set_null_count
    FROM information_schema.referential_constraints
    WHERE constraint_schema = 'public'
      AND delete_rule = 'SET NULL';
    
    RAISE NOTICE 'CASCADE constraints: %', cascade_count;
    RAISE NOTICE 'SET NULL constraints: %', set_null_count;
    
    -- Expected: 15 CASCADE + 9 SET NULL = 24 total
    IF cascade_count < 15 THEN
        RAISE EXCEPTION 'Expected at least 15 CASCADE constraints, got %', cascade_count;
    END IF;
    
    IF set_null_count < 9 THEN
        RAISE EXCEPTION 'Expected at least 9 SET NULL constraints, got %', set_null_count;
    END IF;
    
    RAISE NOTICE 'Migration successful! All constraints updated.';
END $$;

COMMIT;

-- ============================================================================
-- POST-MIGRATION VERIFICATION
-- ============================================================================
-- Run verify_integrity.sql to ensure no orphaned records exist
