-- ============================================================================
-- Migration: Make Nullable Fields NOT NULL
-- ============================================================================
-- Date: 2026-05-22
-- Purpose: Make conversations.paper_id and ai_jobs.paper_id NOT NULL
-- Rationale: All existing records have non-NULL values and business logic
--            requires every conversation/job to belong to a paper
-- Risk: Low - All existing data is valid
-- ============================================================================

BEGIN;

-- Verify we're on the correct database
DO $$
BEGIN
    IF current_database() != 'papergenerator' THEN
        RAISE EXCEPTION 'Wrong database! Expected papergenerator, got %', current_database();
    END IF;
END $$;

\echo '============================================================================'
\echo 'PRE-MIGRATION VALIDATION'
\echo '============================================================================'

-- Check for NULL values before migration
DO $$
DECLARE
    null_conversations INTEGER;
    null_ai_jobs INTEGER;
BEGIN
    SELECT COUNT(*) INTO null_conversations FROM conversations WHERE paper_id IS NULL;
    SELECT COUNT(*) INTO null_ai_jobs FROM ai_jobs WHERE paper_id IS NULL;

    RAISE NOTICE 'Conversations with NULL paper_id: %', null_conversations;
    RAISE NOTICE 'AI jobs with NULL paper_id: %', null_ai_jobs;

    IF null_conversations > 0 THEN
        RAISE EXCEPTION 'Cannot proceed: % conversations have NULL paper_id', null_conversations;
    END IF;

    IF null_ai_jobs > 0 THEN
        RAISE EXCEPTION 'Cannot proceed: % ai_jobs have NULL paper_id', null_ai_jobs;
    END IF;

    RAISE NOTICE 'Validation passed: No NULL values found';
END $$;

\echo ''
\echo '============================================================================'
\echo 'APPLYING NOT NULL CONSTRAINTS'
\echo '============================================================================'

-- Make conversations.paper_id NOT NULL
ALTER TABLE conversations
    ALTER COLUMN paper_id SET NOT NULL;

RAISE NOTICE 'conversations.paper_id is now NOT NULL';

-- Make ai_jobs.paper_id NOT NULL
ALTER TABLE ai_jobs
    ALTER COLUMN paper_id SET NOT NULL;

RAISE NOTICE 'ai_jobs.paper_id is now NOT NULL';

\echo ''
\echo '============================================================================'
\echo 'POST-MIGRATION VERIFICATION'
\echo '============================================================================'

-- Verify constraints are applied
DO $$
DECLARE
    conversations_nullable BOOLEAN;
    ai_jobs_nullable BOOLEAN;
BEGIN
    SELECT is_nullable = 'YES' INTO conversations_nullable
    FROM information_schema.columns
    WHERE table_name = 'conversations' AND column_name = 'paper_id';

    SELECT is_nullable = 'YES' INTO ai_jobs_nullable
    FROM information_schema.columns
    WHERE table_name = 'ai_jobs' AND column_name = 'paper_id';

    IF conversations_nullable THEN
        RAISE EXCEPTION 'conversations.paper_id is still nullable!';
    END IF;

    IF ai_jobs_nullable THEN
        RAISE EXCEPTION 'ai_jobs.paper_id is still nullable!';
    END IF;

    RAISE NOTICE 'Verification passed: Both fields are now NOT NULL';
END $$;

COMMIT;

\echo ''
\echo '============================================================================'
\echo 'MIGRATION COMPLETE'
\echo '============================================================================'
\echo ''
\echo 'Changes applied:'
\echo '  - conversations.paper_id: nullable → NOT NULL'
\echo '  - ai_jobs.paper_id: nullable → NOT NULL'
\echo ''
\echo 'Rollback (if needed):'
\echo '  ALTER TABLE conversations ALTER COLUMN paper_id DROP NOT NULL;'
\echo '  ALTER TABLE ai_jobs ALTER COLUMN paper_id DROP NOT NULL;'
\echo ''
