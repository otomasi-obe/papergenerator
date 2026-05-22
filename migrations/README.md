# Database Migration Guide
**Date:** 2026-05-22  
**Purpose:** Add CASCADE DELETE/SET NULL constraints to prevent orphaned records

---

## Overview

This guide covers applying database migrations to add proper referential integrity constraints at the database level. These constraints ensure that when records are deleted (via ORM or raw SQL), related records are automatically cleaned up or nullified.

---

## Files

```
migrations/
├── fix_cascade_constraints.sql      # Main migration (add CASCADE/SET NULL)
├── rollback_cascade_constraints.sql # Rollback to NO ACTION
├── make_fields_not_null.sql         # Make paper_id fields NOT NULL
└── verify_integrity.sql             # Check for orphaned records

scripts/
└── monitor_db_integrity.sh          # Daily monitoring cron job

DB_INTEGRITY_AUDIT_2026_05_22.md    # Full audit report
```

---

## Pre-Migration Checklist

- [ ] Read the full audit report: `DB_INTEGRITY_AUDIT_2026_05_22.md`
- [ ] Backup the database: `pg_dump papergenerator > backup_pre_migration_$(date +%Y%m%d).sql`
- [ ] Verify current state is clean: `psql -f migrations/verify_integrity.sql`
- [ ] Schedule migration during low-traffic window
- [ ] Notify team of brief downtime (ALTER TABLE locks)
- [ ] Have rollback script ready

---

## Migration Steps

### Step 1: Backup Database

```bash
cd /home/sirobo/papergenerator
mkdir -p backups/migrations
PGPASSWORD=mo2giTAQMcJK3l4eKzq2pk6qNtje4O60 \
  pg_dump -U papergenerator -h localhost papergenerator \
  > backups/migrations/pre_cascade_migration_$(date +%Y%m%d_%H%M%S).sql
```

### Step 2: Verify Current State

```bash
cd /home/sirobo/papergenerator/migrations
PGPASSWORD=mo2giTAQMcJK3l4eKzq2pk6qNtje4O60 \
  psql -U papergenerator -h localhost -d papergenerator \
  -f verify_integrity.sql
```

**Expected:** All orphaned record counts should be 0.

### Step 3: Apply CASCADE Constraints

```bash
cd /home/sirobo/papergenerator/migrations
PGPASSWORD=mo2giTAQMcJK3l4eKzq2pk6qNtje4O60 \
  psql -U papergenerator -h localhost -d papergenerator \
  -f fix_cascade_constraints.sql
```

**Expected output:**
```
NOTICE:  CASCADE constraints: 15
NOTICE:  SET NULL constraints: 9
NOTICE:  Migration successful! All constraints updated.
COMMIT
```

**Duration:** ~2-5 seconds (brief table locks during ALTER TABLE)

### Step 4: Verify Migration Success

```bash
cd /home/sirobo/papergenerator/migrations
PGPASSWORD=mo2giTAQMcJK3l4eKzq2pk6qNtje4O60 \
  psql -U papergenerator -h localhost -d papergenerator \
  -f verify_integrity.sql | grep -A5 "CASCADE CONSTRAINT SUMMARY"
```

**Expected:**
```
 delete_rule | count 
-------------+-------
 CASCADE     |    15
 SET NULL    |     9
```

### Step 5: (Optional) Make Fields NOT NULL

Only apply if you want to enforce that conversations and ai_jobs must always have a paper_id:

```bash
cd /home/sirobo/papergenerator/migrations
PGPASSWORD=mo2giTAQMcJK3l4eKzq2pk6qNtje4O60 \
  psql -U papergenerator -h localhost -d papergenerator \
  -f make_fields_not_null.sql
```

### Step 6: Test Application

```bash
# Restart backend
pm2 restart paper-backend

# Check logs
tail -f /home/sirobo/papergenerator/backend/app.log

# Test basic operations
curl -sf https://paperfull.app/api/healthz && echo "OK"
```

### Step 7: Setup Monitoring

```bash
# Test monitoring script
cd /home/sirobo/papergenerator
./scripts/monitor_db_integrity.sh

# Add to crontab (runs daily at 2 AM)
crontab -e
# Add line:
# 0 2 * * * /home/sirobo/papergenerator/scripts/monitor_db_integrity.sh
```

---

## Rollback Procedure

If issues occur, rollback immediately:

```bash
cd /home/sirobo/papergenerator/migrations
PGPASSWORD=mo2giTAQMcJK3l4eKzq2pk6qNtje4O60 \
  psql -U papergenerator -h localhost -d papergenerator \
  -f rollback_cascade_constraints.sql
```

Or restore from backup:

```bash
# Stop backend
pm2 stop paper-backend

# Drop and recreate database
PGPASSWORD=mo2giTAQMcJK3l4eKzq2pk6qNtje4O60 \
  psql -U papergenerator -h localhost -c "DROP DATABASE papergenerator;"
PGPASSWORD=mo2giTAQMcJK3l4eKzq2pk6qNtje4O60 \
  psql -U papergenerator -h localhost -c "CREATE DATABASE papergenerator;"

# Restore backup
PGPASSWORD=mo2giTAQMcJK3l4eKzq2pk6qNtje4O60 \
  psql -U papergenerator -h localhost papergenerator \
  < backups/migrations/pre_cascade_migration_YYYYMMDD_HHMMSS.sql

# Restart backend
pm2 restart paper-backend
```

---

## Testing CASCADE Behavior

After migration, you can test CASCADE behavior in a safe way:

```sql
-- Create test user
INSERT INTO users (email, name, token_quota_monthly, token_used_month)
VALUES ('test@example.com', 'Test User', 1000000, 0)
RETURNING id;  -- Note the ID

-- Create test paper
INSERT INTO papers (id, user_id, title, data)
VALUES ('test123', <user_id>, 'Test Paper', '{}');

-- Create test conversation
INSERT INTO conversations (id, user_id, paper_id, title)
VALUES ('testconv', <user_id>, 'test123', 'Test Conversation');

-- Verify records exist
SELECT COUNT(*) FROM papers WHERE id = 'test123';
SELECT COUNT(*) FROM conversations WHERE paper_id = 'test123';

-- Delete paper (should CASCADE delete conversation)
DELETE FROM papers WHERE id = 'test123';

-- Verify conversation was deleted
SELECT COUNT(*) FROM conversations WHERE paper_id = 'test123';
-- Expected: 0

-- Cleanup test user
DELETE FROM users WHERE email = 'test@example.com';
```

---

## What Changed

### Before Migration
- Foreign keys exist but have NO ACTION on delete
- Deleting a user/paper via raw SQL leaves orphaned records
- Only SQLAlchemy ORM deletes clean up related records

### After Migration
- 15 foreign keys have CASCADE DELETE
- 9 foreign keys have SET NULL
- Deleting a user/paper via ANY method (ORM or raw SQL) automatically cleans up related records
- Database enforces referential integrity at the DB level

---

## Impact Analysis

### Performance
- **Minimal impact** - CASCADE operations are efficient in PostgreSQL
- ALTER TABLE operations take ~2-5 seconds total
- No ongoing performance penalty

### Application Code
- **No code changes required** - Application continues to work as before
- SQLAlchemy cascade behaviors still work (now redundant but harmless)
- Raw SQL deletes now properly clean up related records

### Data Safety
- **Improved** - Prevents orphaned records from any deletion path
- **Defense in depth** - Protection at both ORM and DB level
- **Monitoring** - Daily cron job alerts if orphaned records appear

---

## Monitoring

After migration, monitor for:

1. **Daily integrity checks** - Automated via cron
2. **Application logs** - Watch for foreign key errors
3. **Database logs** - Monitor CASCADE operations

Check logs:
```bash
# Application logs
tail -f /home/sirobo/papergenerator/backend/app.log

# Integrity check logs
tail -f /home/sirobo/papergenerator/logs/db_integrity_*.log

# PostgreSQL logs (if enabled)
tail -f /var/log/postgresql/postgresql-*.log
```

---

## FAQ

**Q: Will this delete any existing data?**  
A: No. The migration only changes constraint behavior. No data is deleted during migration.

**Q: What happens if I delete a user?**  
A: All their papers, conversations, images, files, and memory will be CASCADE deleted. Jobs and logs will have user_id set to NULL.

**Q: Can I rollback after running for a week?**  
A: Yes, but be aware that if CASCADE deletes have occurred, rolling back won't restore those deleted records. Always backup first.

**Q: Do I need to update application code?**  
A: No. The application continues to work exactly as before.

**Q: What if migration fails mid-way?**  
A: The migration runs in a transaction (BEGIN/COMMIT). If any step fails, all changes are rolled back automatically.

---

## Support

If issues occur:
1. Check logs: `tail -f /home/sirobo/papergenerator/backend/app.log`
2. Run verification: `psql -f migrations/verify_integrity.sql`
3. Review audit report: `DB_INTEGRITY_AUDIT_2026_05_22.md`
4. Rollback if needed: `psql -f migrations/rollback_cascade_constraints.sql`

---

## Summary

✅ **Current State:** Database is clean, no orphaned records  
⚠️ **Risk:** Missing CASCADE constraints could lead to orphaned records  
🎯 **Solution:** Apply migration to add CASCADE/SET NULL at DB level  
📊 **Monitoring:** Daily cron job alerts if issues detected  
🔄 **Rollback:** Available if needed
