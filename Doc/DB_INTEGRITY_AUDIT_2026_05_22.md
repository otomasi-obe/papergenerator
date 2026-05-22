# Database Integrity Audit Report
**Date:** 2026-05-22  
**Database:** papergenerator (PostgreSQL)  
**Auditor:** Kilo  
**Context:** Post-incident audit following accidental production DB drop (LAPORAN_2026_05_22.md)

---

## Executive Summary

✅ **Current State: CLEAN** - No orphaned records found  
⚠️ **Critical Risk: Missing CASCADE DELETE constraints at database level**  
✅ **Safety Mechanisms: Working** - Test isolation and drop_all guards in place

### Key Metrics
| Metric | Status |
|--------|--------|
| Orphaned records | **0** (all clean) |
| Total records | **2,121** across 12 tables |
| Foreign key constraints | **24 defined** |
| CASCADE DELETE constraints | **1 of 24** (4%) |
| Safety guards | **2 active** (conftest.py + models.py) |

---

## 1. Orphaned Records Check ✅

All orphaned record checks returned **0 results**:

```sql
-- Orphaned papers (user deleted but papers remain)
SELECT COUNT(*) FROM papers WHERE user_id NOT IN (SELECT id FROM users);
-- Result: 0

-- Orphaned conversations (paper deleted but conversations remain)
SELECT COUNT(*) FROM conversations 
WHERE paper_id IS NOT NULL AND paper_id NOT IN (SELECT id FROM papers);
-- Result: 0

-- Orphaned chat_messages (conversation deleted but messages remain)
SELECT COUNT(*) FROM chat_messages 
WHERE conversation_id NOT IN (SELECT id FROM conversations);
-- Result: 0

-- Orphaned ai_jobs (paper deleted but jobs remain)
SELECT COUNT(*) FROM ai_jobs 
WHERE paper_id IS NOT NULL AND paper_id NOT IN (SELECT id FROM papers);
-- Result: 0

-- Orphaned slr_jobs (paper deleted but jobs remain)
SELECT COUNT(*) FROM slr_jobs WHERE paper_id NOT IN (SELECT id FROM papers);
-- Result: 0

-- Orphaned image_gen_jobs (paper deleted but jobs remain)
SELECT COUNT(*) FROM image_gen_jobs WHERE paper_id NOT IN (SELECT id FROM papers);
-- Result: 0

-- Orphaned literature_items (paper deleted but items remain)
SELECT COUNT(*) FROM literature_items WHERE paper_id NOT IN (SELECT id FROM papers);
-- Result: 0

-- Literature items with invalid file_id
SELECT COUNT(*) FROM literature_items 
WHERE file_id IS NOT NULL AND file_id NOT IN (SELECT id FROM paper_files);
-- Result: 0

-- Image gen jobs with invalid image_id
SELECT COUNT(*) FROM image_gen_jobs 
WHERE image_id IS NOT NULL AND image_id NOT IN (SELECT id FROM paper_images);
-- Result: 0
```

**Conclusion:** Database is currently consistent. No cleanup needed.

---

## 2. Critical Issue: Missing CASCADE DELETE Constraints ⚠️

### Problem
SQLAlchemy models define `cascade='all, delete-orphan'` on relationships, but these **only work when using ORM methods** like `db.session.delete()`. They do NOT protect against:
- Raw SQL `DELETE` statements
- Database-level operations
- Bugs that bypass the ORM
- Direct database access

### Current State
Only **1 of 24** foreign key constraints has CASCADE DELETE at the database level:
- ✅ `project_memory.conversation_id` → `ON DELETE CASCADE`
- ✅ `literature_items.slr_job_id` → `ON DELETE SET NULL`

All other foreign keys have **NO CASCADE behavior** at the database level.

### Impact
If a user or paper is deleted via raw SQL (or a bug bypasses ORM), orphaned records will remain in:
- `papers` (when user deleted)
- `paper_images` (when paper or user deleted)
- `paper_files` (when paper or user deleted)
- `conversations` (when paper or user deleted)
- `chat_messages` (when conversation deleted)
- `project_memory` (when paper deleted)
- `ai_jobs` (when paper or user deleted)
- `slr_jobs` (when paper, user, or conversation deleted)
- `image_gen_jobs` (when paper or user deleted)
- `literature_items` (when paper, user, or file deleted)

### Recommended CASCADE Strategy

| Foreign Key | Current | Recommended | Rationale |
|-------------|---------|-------------|-----------|
| `papers.user_id` | NO ACTION | **CASCADE** | User owns papers; delete papers when user deleted |
| `paper_images.paper_id` | NO ACTION | **CASCADE** | Images belong to paper; delete when paper deleted |
| `paper_images.user_id` | NO ACTION | **CASCADE** | Delete user's images when user deleted |
| `paper_files.paper_id` | NO ACTION | **CASCADE** | Files belong to paper; delete when paper deleted |
| `paper_files.user_id` | NO ACTION | **CASCADE** | Delete user's files when user deleted |
| `conversations.paper_id` | NO ACTION | **CASCADE** | Conversations belong to paper; delete when paper deleted |
| `conversations.user_id` | NO ACTION | **CASCADE** | Delete user's conversations when user deleted |
| `chat_messages.conversation_id` | NO ACTION | **CASCADE** | Messages belong to conversation; delete when conversation deleted |
| `project_memory.paper_id` | NO ACTION | **CASCADE** | Memory belongs to paper; delete when paper deleted |
| `project_memory.conversation_id` | **CASCADE** ✓ | CASCADE | Already correct |
| `project_memory.user_id` | NO ACTION | **CASCADE** | Delete user's memory when user deleted |
| `ai_jobs.paper_id` | NO ACTION | **SET NULL** | Keep job history even if paper deleted |
| `ai_jobs.user_id` | NO ACTION | **SET NULL** | Keep job history even if user deleted |
| `slr_jobs.paper_id` | NO ACTION | **CASCADE** | SLR jobs belong to paper; delete when paper deleted |
| `slr_jobs.user_id` | NO ACTION | **SET NULL** | Keep job history even if user deleted |
| `slr_jobs.conversation_id` | NO ACTION | **SET NULL** | Keep job even if conversation deleted |
| `image_gen_jobs.paper_id` | NO ACTION | **CASCADE** | Image jobs belong to paper; delete when paper deleted |
| `image_gen_jobs.user_id` | NO ACTION | **SET NULL** | Keep job history even if user deleted |
| `image_gen_jobs.image_id` | NO ACTION | **SET NULL** | Keep job even if image deleted |
| `literature_items.paper_id` | NO ACTION | **CASCADE** | Literature belongs to paper; delete when paper deleted |
| `literature_items.user_id` | NO ACTION | **CASCADE** | Delete user's literature when user deleted |
| `literature_items.file_id` | NO ACTION | **SET NULL** | Keep literature item even if file deleted |
| `literature_items.slr_job_id` | **SET NULL** ✓ | SET NULL | Already correct |
| `api_usage_logs.user_id` | NO ACTION | **SET NULL** | Keep logs for analytics even if user deleted |

---

## 3. Data Consistency Issues

### Nullable Fields Analysis

| Table | Field | Nullable | Current NULL Count | Issue? |
|-------|-------|----------|-------------------|--------|
| `conversations.paper_id` | paper_id | YES | 0 | ⚠️ Should be NOT NULL |
| `ai_jobs.paper_id` | paper_id | YES | 0 | ⚠️ Should be NOT NULL |

**Recommendation:** Make these fields NOT NULL since:
1. All existing records have non-NULL values
2. Business logic requires every conversation/job to belong to a paper
3. Prevents future bugs from creating orphaned conversations/jobs

---

## 4. Safety Mechanisms Verification ✅

### Test Database Isolation
**File:** `backend/tests/conftest.py:1-30`

```python
# Force in-memory test DB regardless of any inherited DATABASE_URL
_db = os.environ.get("DATABASE_URL", "")
if not _db.startswith("sqlite:"):
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Belt-and-suspenders: refuse to run against any host that looks like a real DB
_url = os.environ["DATABASE_URL"]
if not _url.startswith("sqlite:"):
    raise RuntimeError(
        f"Test suite refuses to run against non-sqlite DATABASE_URL: {_url!r}"
    )
```

**Status:** ✅ Working - Forces sqlite for all tests, prevents production DB access

### Production Drop Protection
**File:** `backend/models.py:490-517`

```python
def _safe_drop_all(*args, **kwargs):
    try:
        url = str(db.engine.url)
    except Exception:
        raise RuntimeError(
            "db.drop_all() refused: no active app context to verify the bound DB."
        )
    is_sqlite = url.startswith('sqlite:')
    allow = _os.environ.get('PAPERFULL_ALLOW_DESTRUCTIVE_DB') == '1'
    if not is_sqlite and not allow:
        raise RuntimeError(
            f"db.drop_all() refused: connected DB is not sqlite ({url!r}). "
            "Set PAPERFULL_ALLOW_DESTRUCTIVE_DB=1 only when you really mean it."
        )
    return _real_drop_all(*args, **kwargs)

db.drop_all = _safe_drop_all
```

**Status:** ✅ Working - Refuses to drop production DB unless explicitly allowed

### Backup System
**Evidence:** `backups/daily/pg-2026-05-22.sql.gz` (mentioned in incident report)

**Status:** ✅ Exists - Daily backups enabled recovery after incident

---

## 5. Database Statistics

```
Total records: 2,121
├── users:            43
├── papers:           54
├── conversations:    57
├── chat_messages:   543
├── ai_jobs:          12
├── slr_jobs:         26
├── image_gen_jobs:    4
├── literature_items: 963
├── paper_images:      5
├── paper_files:      63
├── project_memory:   27
└── api_usage_logs:  324
```

---

## 6. Recommendations

### Priority 1: Add CASCADE DELETE Constraints (HIGH)
Apply migration script `fix_cascade_constraints.sql` to add proper CASCADE DELETE/SET NULL behaviors at the database level.

**Risk:** Medium - Requires ALTER TABLE operations, brief table locks  
**Benefit:** High - Prevents orphaned records from any deletion path  
**Rollback:** Available via `rollback_cascade_constraints.sql`

### Priority 2: Make Nullable Fields NOT NULL (MEDIUM)
Make `conversations.paper_id` and `ai_jobs.paper_id` NOT NULL since all existing records have values and business logic requires them.

**Risk:** Low - All existing data is valid  
**Benefit:** Medium - Prevents future bugs  
**Rollback:** Available

### Priority 3: Add Monitoring (LOW)
Create a daily cron job to run orphaned record checks and alert if any found.

**Risk:** None  
**Benefit:** Early detection of integrity issues

---

## 7. Migration Scripts

See attached files:
- `fix_cascade_constraints.sql` - Add CASCADE DELETE/SET NULL to all foreign keys
- `rollback_cascade_constraints.sql` - Revert to NO ACTION if needed
- `verify_integrity.sql` - Run orphaned record checks
- `make_fields_not_null.sql` - Make paper_id fields NOT NULL

---

## 8. Conclusion

**Current State:** Database is clean with no orphaned records. Safety mechanisms are working.

**Critical Gap:** Missing CASCADE DELETE constraints at database level create risk of orphaned records if ORM is bypassed.

**Action Required:** Apply migration scripts to add proper CASCADE behaviors at database level for defense-in-depth.

**Next Steps:**
1. Review and approve migration scripts
2. Test migrations on staging/backup database
3. Apply to production during low-traffic window
4. Verify with `verify_integrity.sql`
5. Set up monitoring for future integrity checks
