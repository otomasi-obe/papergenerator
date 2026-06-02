-- ============================================================================
-- Database Integrity Verification Queries
-- ============================================================================
-- Date: 2026-05-22
-- Purpose: Check for orphaned records and data inconsistencies
-- Usage: Run after migrations or periodically for monitoring
-- ============================================================================

\echo '============================================================================'
\echo 'DATABASE INTEGRITY VERIFICATION'
\echo '============================================================================'
\echo ''

-- Verify database
SELECT current_database() as database, current_user as user, now() as timestamp;

\echo ''
\echo '--- 1. ORPHANED RECORDS CHECK ---'
\echo ''

-- Orphaned papers (user deleted but papers remain)
\echo 'Checking for orphaned papers...'
SELECT COUNT(*) as orphaned_papers
FROM papers
WHERE user_id NOT IN (SELECT id FROM users);

-- Orphaned conversations (paper deleted but conversations remain)
\echo 'Checking for orphaned conversations...'
SELECT COUNT(*) as orphaned_conversations
FROM conversations
WHERE paper_id IS NOT NULL
  AND paper_id NOT IN (SELECT id FROM papers);

-- Orphaned chat_messages (conversation deleted but messages remain)
\echo 'Checking for orphaned chat_messages...'
SELECT COUNT(*) as orphaned_chat_messages
FROM chat_messages
WHERE conversation_id NOT IN (SELECT id FROM conversations);

-- Orphaned ai_jobs (paper deleted but jobs remain)
\echo 'Checking for orphaned ai_jobs...'
SELECT COUNT(*) as orphaned_ai_jobs
FROM ai_jobs
WHERE paper_id IS NOT NULL
  AND paper_id NOT IN (SELECT id FROM papers);

-- Orphaned slr_jobs (paper deleted but jobs remain)
\echo 'Checking for orphaned slr_jobs...'
SELECT COUNT(*) as orphaned_slr_jobs
FROM slr_jobs
WHERE paper_id NOT IN (SELECT id FROM papers);

-- Orphaned image_gen_jobs (paper deleted but jobs remain)
\echo 'Checking for orphaned image_gen_jobs...'
SELECT COUNT(*) as orphaned_image_gen_jobs
FROM image_gen_jobs
WHERE paper_id NOT IN (SELECT id FROM papers);

-- Orphaned literature_items (paper deleted but items remain)
\echo 'Checking for orphaned literature_items...'
SELECT COUNT(*) as orphaned_literature_items
FROM literature_items
WHERE paper_id NOT IN (SELECT id FROM papers);

-- Literature items with invalid file_id
\echo 'Checking for literature_items with invalid file_id...'
SELECT COUNT(*) as literature_items_invalid_file
FROM literature_items
WHERE file_id IS NOT NULL
  AND file_id NOT IN (SELECT id FROM paper_files);

-- Image gen jobs with invalid image_id
\echo 'Checking for image_gen_jobs with invalid image_id...'
SELECT COUNT(*) as image_gen_jobs_invalid_image
FROM image_gen_jobs
WHERE image_id IS NOT NULL
  AND image_id NOT IN (SELECT id FROM paper_images);

-- Orphaned paper_images (paper deleted but images remain)
\echo 'Checking for orphaned paper_images...'
SELECT COUNT(*) as orphaned_paper_images
FROM paper_images
WHERE paper_id NOT IN (SELECT id FROM papers);

-- Orphaned paper_files (paper deleted but files remain)
\echo 'Checking for orphaned paper_files...'
SELECT COUNT(*) as orphaned_paper_files
FROM paper_files
WHERE paper_id NOT IN (SELECT id FROM papers);

-- Orphaned project_memory (paper deleted but memory remains)
\echo 'Checking for orphaned project_memory...'
SELECT COUNT(*) as orphaned_project_memory
FROM project_memory
WHERE paper_id NOT IN (SELECT id FROM papers);

\echo ''
\echo '--- 2. NULL VALUE CHECKS ---'
\echo ''

-- Conversations without papers
\echo 'Checking for conversations without papers...'
SELECT COUNT(*) as conversations_without_paper
FROM conversations
WHERE paper_id IS NULL;

-- AI jobs without papers
\echo 'Checking for ai_jobs without papers...'
SELECT COUNT(*) as ai_jobs_without_paper
FROM ai_jobs
WHERE paper_id IS NULL;

\echo ''
\echo '--- 3. RECORD COUNTS ---'
\echo ''

SELECT 'users' as table_name, COUNT(*) as count FROM users
UNION ALL SELECT 'papers', COUNT(*) FROM papers
UNION ALL SELECT 'conversations', COUNT(*) FROM conversations
UNION ALL SELECT 'chat_messages', COUNT(*) FROM chat_messages
UNION ALL SELECT 'ai_jobs', COUNT(*) FROM ai_jobs
UNION ALL SELECT 'slr_jobs', COUNT(*) FROM slr_jobs
UNION ALL SELECT 'image_gen_jobs', COUNT(*) FROM image_gen_jobs
UNION ALL SELECT 'literature_items', COUNT(*) FROM literature_items
UNION ALL SELECT 'paper_images', COUNT(*) FROM paper_images
UNION ALL SELECT 'paper_files', COUNT(*) FROM paper_files
UNION ALL SELECT 'project_memory', COUNT(*) FROM project_memory
UNION ALL SELECT 'api_usage_logs', COUNT(*) FROM api_usage_logs
ORDER BY table_name;

\echo ''
\echo '--- 4. FOREIGN KEY CONSTRAINT STATUS ---'
\echo ''

SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    rc.delete_rule
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
    AND ccu.table_schema = tc.table_schema
JOIN information_schema.referential_constraints AS rc
    ON rc.constraint_name = tc.constraint_name
    AND rc.constraint_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
    AND tc.table_schema = 'public'
ORDER BY tc.table_name, kcu.column_name;

\echo ''
\echo '--- 5. CASCADE CONSTRAINT SUMMARY ---'
\echo ''

SELECT
    delete_rule,
    COUNT(*) as count
FROM information_schema.referential_constraints
WHERE constraint_schema = 'public'
GROUP BY delete_rule
ORDER BY delete_rule;

\echo ''
\echo '============================================================================'
\echo 'VERIFICATION COMPLETE'
\echo '============================================================================'
\echo ''
\echo 'Expected results:'
\echo '  - All orphaned record counts should be 0'
\echo '  - After migration: CASCADE ~15, SET NULL ~9, NO ACTION 0'
\echo '  - Before migration: NO ACTION ~22, CASCADE 1, SET NULL 1'
\echo ''
