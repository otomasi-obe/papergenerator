#!/bin/bash
# ============================================================================
# Database Integrity Monitor
# ============================================================================
# Purpose: Daily cron job to check for orphaned records and alert if found
# Usage: Add to crontab: 0 2 * * * /path/to/monitor_db_integrity.sh
# ============================================================================

set -euo pipefail

# Configuration
DB_NAME="papergenerator"
DB_USER="papergenerator"
DB_HOST="localhost"
ALERT_EMAIL="admin@paperfull.app"
LOG_FILE="/home/sirobo/papergenerator/logs/db_integrity_$(date +%Y%m%d).log"
ALERT_THRESHOLD=0  # Alert if any orphaned records found

# Load DB password from .env
if [ -f "/home/sirobo/papergenerator/backend/.env" ]; then
    export $(grep "^DATABASE_URL=" /home/sirobo/papergenerator/backend/.env | cut -d'=' -f2- | sed 's/.*:\/\/[^:]*:\([^@]*\)@.*/PGPASSWORD=\1/')
fi

# Create log directory if it doesn't exist
mkdir -p "$(dirname "$LOG_FILE")"

# Timestamp
echo "============================================================================" | tee -a "$LOG_FILE"
echo "Database Integrity Check - $(date)" | tee -a "$LOG_FILE"
echo "============================================================================" | tee -a "$LOG_FILE"

# Function to run query and return count
check_orphaned() {
    local query="$1"
    local description="$2"
    
    count=$(PGPASSWORD="$PGPASSWORD" psql -U "$DB_USER" -h "$DB_HOST" -d "$DB_NAME" -t -c "$query" 2>&1 | xargs)
    
    if [ "$count" -gt "$ALERT_THRESHOLD" ]; then
        echo "❌ ALERT: $description - Found $count orphaned records" | tee -a "$LOG_FILE"
        return 1
    else
        echo "✅ OK: $description - No orphaned records" | tee -a "$LOG_FILE"
        return 0
    fi
}

# Track if any issues found
issues_found=0

# Check for orphaned records
check_orphaned "SELECT COUNT(*) FROM papers WHERE user_id NOT IN (SELECT id FROM users);" \
    "Orphaned papers" || issues_found=$((issues_found + 1))

check_orphaned "SELECT COUNT(*) FROM conversations WHERE paper_id IS NOT NULL AND paper_id NOT IN (SELECT id FROM papers);" \
    "Orphaned conversations" || issues_found=$((issues_found + 1))

check_orphaned "SELECT COUNT(*) FROM chat_messages WHERE conversation_id NOT IN (SELECT id FROM conversations);" \
    "Orphaned chat_messages" || issues_found=$((issues_found + 1))

check_orphaned "SELECT COUNT(*) FROM ai_jobs WHERE paper_id IS NOT NULL AND paper_id NOT IN (SELECT id FROM papers);" \
    "Orphaned ai_jobs" || issues_found=$((issues_found + 1))

check_orphaned "SELECT COUNT(*) FROM slr_jobs WHERE paper_id NOT IN (SELECT id FROM papers);" \
    "Orphaned slr_jobs" || issues_found=$((issues_found + 1))

check_orphaned "SELECT COUNT(*) FROM image_gen_jobs WHERE paper_id NOT IN (SELECT id FROM papers);" \
    "Orphaned image_gen_jobs" || issues_found=$((issues_found + 1))

check_orphaned "SELECT COUNT(*) FROM literature_items WHERE paper_id NOT IN (SELECT id FROM papers);" \
    "Orphaned literature_items" || issues_found=$((issues_found + 1))

check_orphaned "SELECT COUNT(*) FROM literature_items WHERE file_id IS NOT NULL AND file_id NOT IN (SELECT id FROM paper_files);" \
    "Literature items with invalid file_id" || issues_found=$((issues_found + 1))

check_orphaned "SELECT COUNT(*) FROM image_gen_jobs WHERE image_id IS NOT NULL AND image_id NOT IN (SELECT id FROM paper_images);" \
    "Image gen jobs with invalid image_id" || issues_found=$((issues_found + 1))

check_orphaned "SELECT COUNT(*) FROM paper_images WHERE paper_id NOT IN (SELECT id FROM papers);" \
    "Orphaned paper_images" || issues_found=$((issues_found + 1))

check_orphaned "SELECT COUNT(*) FROM paper_files WHERE paper_id NOT IN (SELECT id FROM papers);" \
    "Orphaned paper_files" || issues_found=$((issues_found + 1))

check_orphaned "SELECT COUNT(*) FROM project_memory WHERE paper_id NOT IN (SELECT id FROM papers);" \
    "Orphaned project_memory" || issues_found=$((issues_found + 1))

# Summary
echo "" | tee -a "$LOG_FILE"
echo "============================================================================" | tee -a "$LOG_FILE"
if [ "$issues_found" -eq 0 ]; then
    echo "✅ Database integrity check PASSED - No issues found" | tee -a "$LOG_FILE"
    exit 0
else
    echo "❌ Database integrity check FAILED - $issues_found issue(s) found" | tee -a "$LOG_FILE"
    
    # Send alert email (requires mailx or sendmail)
    if command -v mail &> /dev/null; then
        echo "Database integrity issues detected. See log: $LOG_FILE" | \
            mail -s "⚠️ PaperFull DB Integrity Alert" "$ALERT_EMAIL"
    fi
    
    exit 1
fi
