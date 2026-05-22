#!/bin/bash
# Quick Reference: Database Integrity Audit & Migration
# ============================================================================

cat << 'EOF'
╔══════════════════════════════════════════════════════════════════════════╗
║                  DATABASE INTEGRITY AUDIT - QUICK REFERENCE              ║
║                           Date: 2026-05-22                               ║
╚══════════════════════════════════════════════════════════════════════════╝

📊 CURRENT STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Database is CLEAN - 0 orphaned records
⚠️  Missing CASCADE DELETE constraints (22 of 24 foreign keys)
✅ Safety mechanisms working (test isolation + drop guards)
✅ Backup system exists

📁 DELIVERABLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reports:
  • DB_INTEGRITY_AUDIT_2026_05_22.md    - Full audit (8 sections)
  • MIGRATION_SUMMARY.md                 - Executive summary
  • AUDIT_FINAL_REPORT.md                - Final report with stats

Migration Scripts:
  • migrations/fix_cascade_constraints.sql      - Add CASCADE/SET NULL
  • migrations/rollback_cascade_constraints.sql - Rollback if needed
  • migrations/make_fields_not_null.sql         - Make paper_id NOT NULL
  • migrations/verify_integrity.sql             - Check orphaned records

Monitoring:
  • scripts/monitor_db_integrity.sh             - Daily cron job

Documentation:
  • migrations/README.md                        - Detailed guide + FAQ

🚀 QUICK START
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Review audit report:
   cat DB_INTEGRITY_AUDIT_2026_05_22.md

2. Backup database:
   pg_dump papergenerator > backup_$(date +%Y%m%d).sql

3. Apply migration:
   psql -f migrations/fix_cascade_constraints.sql

4. Verify:
   psql -f migrations/verify_integrity.sql

5. Setup monitoring:
   ./scripts/monitor_db_integrity.sh  # Test
   crontab -e  # Add: 0 2 * * * /path/to/monitor_db_integrity.sh

⚡ ONE-LINER COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Verify current state
PGPASSWORD=mo2giTAQMcJK3l4eKzq2pk6qNtje4O60 \
  psql -U papergenerator -h localhost -d papergenerator \
  -f migrations/verify_integrity.sql

# Backup database
PGPASSWORD=mo2giTAQMcJK3l4eKzq2pk6qNtje4O60 \
  pg_dump -U papergenerator -h localhost papergenerator \
  > backups/pre_cascade_$(date +%Y%m%d_%H%M%S).sql

# Apply migration
PGPASSWORD=mo2giTAQMcJK3l4eKzq2pk6qNtje4O60 \
  psql -U papergenerator -h localhost -d papergenerator \
  -f migrations/fix_cascade_constraints.sql

# Rollback (if needed)
PGPASSWORD=mo2giTAQMcJK3l4eKzq2pk6qNtje4O60 \
  psql -U papergenerator -h localhost -d papergenerator \
  -f migrations/rollback_cascade_constraints.sql

📈 EXPECTED RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before Migration:
  CASCADE:    1 constraint  (4%)
  SET NULL:   1 constraint  (4%)
  NO ACTION: 22 constraints (92%)

After Migration:
  CASCADE:   15 constraints (63%)
  SET NULL:   9 constraints (37%)
  NO ACTION:  0 constraints (0%)

🔍 WHAT WAS CHECKED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Orphaned papers (user deleted but papers remain)           → 0
✅ Orphaned conversations (paper deleted but convs remain)    → 0
✅ Orphaned chat_messages (conversation deleted)              → 0
✅ Orphaned ai_jobs (paper deleted but jobs remain)           → 0
✅ Orphaned slr_jobs (paper deleted but jobs remain)          → 0
✅ Orphaned image_gen_jobs (paper deleted but jobs remain)    → 0
✅ Orphaned literature_items (paper deleted but items remain) → 0
✅ Invalid file_id references in literature_items             → 0
✅ Invalid image_id references in image_gen_jobs              → 0
✅ Orphaned paper_images (paper deleted but images remain)    → 0
✅ Orphaned paper_files (paper deleted but files remain)      → 0
✅ Orphaned project_memory (paper deleted but memory remains) → 0

⚠️  CRITICAL FINDING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Missing CASCADE DELETE constraints at database level.

SQLAlchemy cascade='all, delete-orphan' only works via ORM.
Raw SQL deletes will leave orphaned records.

Solution: Apply fix_cascade_constraints.sql

🛡️  SAFETY MECHANISMS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ backend/tests/conftest.py:1-30
   Forces sqlite for tests, prevents production DB access

✅ backend/models.py:490-517
   Refuses to drop production DB unless PAPERFULL_ALLOW_DESTRUCTIVE_DB=1

✅ backups/daily/pg-2026-05-22.sql.gz
   Daily backups enabled recovery from previous incident

⏱️  TIMELINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Review audit:        15 min
Backup database:      2 min
Apply migration:      5 sec  (brief table locks)
Verify migration:     1 min
Setup monitoring:     5 min
─────────────────────────────
Total:              ~25 min

🎯 PRIORITY ACTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Priority 1 (HIGH):   Apply CASCADE constraints
Priority 2 (MEDIUM): Setup monitoring cron job
Priority 3 (LOW):    Make paper_id fields NOT NULL

📞 SUPPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Check logs:          tail -f backend/app.log
Run verification:    psql -f migrations/verify_integrity.sql
Review audit:        cat DB_INTEGRITY_AUDIT_2026_05_22.md
Rollback:            psql -f migrations/rollback_cascade_constraints.sql

╔══════════════════════════════════════════════════════════════════════════╗
║  Database is CLEAN. Migration ready. Rollback available.                ║
╚══════════════════════════════════════════════════════════════════════════╝
EOF
