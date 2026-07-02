# Critical Bug Report — SLR System
**Date:** 2026-06-30  
**Status:** 2 CRITICAL bugs fixed, 8 HIGH/MEDIUM bugs identified

---

## ✅ FIXED (Already Applied)

### 1. [CRITICAL] Status Typo — SLR Stuck at 78%
**File:** `tools/Literatur/slr.py:2533`  
**Bug:** `job.status = "completed"` instead of `"done"`  
**Impact:** Frontend never detects completion. Job stuck forever.  
**Fix Applied:** Changed to `job.status = "done"` ✅

### 2. [HIGH] Missing "analyzing" in Status Map
**File:** `tools/Literatur/slr.py:2563`  
**Bug:** `_set_stage` didn't set `status = "analyzing"`  
**Impact:** Status stayed "pending" during analysis (0-10%)  
**Fix Applied:** Added "analyzing" to status list ✅

### 3. [CRITICAL] Redis TTL Too Short
**File:** `tools/Literatur/slr.py:64`  
**Bug:** `REDIS_PROGRESS_TTL = 600` (10 min). SLR takes 15+ min.  
**Impact:** Redis key expires → frontend loses progress updates  
**Fix Applied:** Increased to `10800` (3 hours) ✅

---

## 🔥 CRITICAL (Need Immediate Fix)

### 4. [CRITICAL] Orchestrator Jobs Not Persisted to DB
**File:** `tools/Literatur/slr.py` (entire orchestrator)  
**Bug:** In-memory `SLRJob` never saved to DB `SlrJob` table. Only Redis stores progress.  
**Impact:** Server restart = ALL running/completed orch jobs LOST. Only legacy worker.py jobs survive.  
**Root Cause:** Orchestrator v3 is pure in-memory + Redis. `_save_to_db()` saves `LiteratureItem` but NOT the job record.

**Fix Required:**
```python
def _persist_job_to_db(job: SLRJob):
    """Persist orchestrator job to DB SlrJob table."""
    from utils.database.models import SlrJob as DbSlrJob, db, safe_commit
    
    db_job = db.session.query(DbSlrJob).filter_by(id=job.job_id).first()
    if not db_job:
        db_job = DbSlrJob(
            id=job.job_id,
            user_id=job.user_id,
            paper_id=job.paper_id,
            query=job.keyword,
            top_k=job.top_n,
            status=job.status,
            stage=job.stage,
            progress=int(job.progress_pct),
            progress_message=job.stage_detail,
        )
        db.session.add(db_job)
    else:
        db_job.status = job.status
        db_job.stage = job.stage
        db_job.progress = int(job.progress_pct)
        db_job.progress_message = job.stage_detail
        if job.status == "done":
            db_job.finished_at = datetime.now(timezone.utc)
        elif job.status == "error":
            db_job.error = job.error or ""
            db_job.finished_at = datetime.now(timezone.utc)
    
    try:
        safe_commit()
    except Exception as e:
        db.session.rollback()
        log.warning("Failed to persist job %s: %s", job.job_id, e)

# Call in:
# 1. start_job() after job creation
# 2. _push_progress() after each update
# 3. _run_pipeline() at completion/error
```

**Where to Call:**
- Line 2269 (after job creation): `_persist_job_to_db(job)`
- Line 2125 (in `_push_progress`): `_persist_job_to_db(job)` (every 5th push to reduce DB load)
- Line 2533 (completion): `_persist_job_to_db(job)`
- Line 2572 (_set_error): `_persist_job_to_db(job)`

---

### 5. [HIGH] Flask App Import Fails in _save_to_db
**File:** `tools/Literatur/slr.py:2621`  
**Bug:** `from main import app as _flask_app` — might fail if module name changes  
**Impact:** If import fails, LiteratureItems NOT saved. User sees 0 items despite SLR completing.

**Fix Required:**
```python
# Replace line 2617-2631
ctx = None
try:
    from flask import current_app
    if current_app:
        ctx = current_app.app_context()
        ctx.push()
    else:
        # Fallback to main import
        try:
            from main import app as _flask_app
            ctx = _flask_app.app_context()
            ctx.push()
        except ImportError:
            log.error("Flask app not available, skipping DB save")
            return
except Exception as e:
    log.error("Failed to get Flask app context: %s", e)
    return
```

---

## ⚠️ HIGH Priority (Fix Soon)

### 6. [HIGH] Field Name Mismatch DB vs In-Memory
**File:** `tools/Literatur/slr.py:2071-2106` (to_dict)  
**Bug:** In-memory `SLRJob` uses `progress_pct`, `stage_detail`. DB `SlrJob` uses `progress`, `progress_message`. Frontend expects `progress` + `progress_message`.  
**Impact:** Inconsistent field names between orch jobs (Redis) vs legacy jobs (DB). Frontend handles both but it's fragile.

**Fix Required:**
Standardize on ONE field naming:
- Option A: In-memory SLRJob.to_dict() always returns `progress` + `progress_message` (current, seems working)
- Option B: Change DB model to use `progress_pct` + `stage_detail` (breaking change)

**Current workaround:** Line 2087-2090 maps both. Keep this but document it clearly.

---

### 7. [HIGH] Long-Poll Might Miss Orch Jobs
**File:** `tools/Literatur/slr.py:566-583`  
**Bug:** Long-poll checks `ts > after` from DB `updated_at`, then adds orch jobs. If ONLY orch jobs updated (no DB jobs), might return stale DB jobs.  
**Impact:** Frontend might not see latest orch job status immediately.

**Fix Required:**
```python
# Line 566: Change condition
if ts > after or new_jobs_active or (orch_jobs and len(orch_jobs) > 0):
    # ... return jobs
```

---

## 📝 MEDIUM Priority

### 8. [MEDIUM] Only 100 Papers Saved
**File:** `tools/Literatur/slr.py:2686-2687`  
**Bug:** `if saved >= 100: break` — hard cap at 100 items  
**Impact:** User fetches 175 papers but only sees 100 in table

**Fix:** Increase to `500` or make configurable via env var

---

### 9. [MEDIUM] URL Uses PDF Fallback
**File:** `tools/Literatur/slr.py:2671`  
**Bug:** `url=(p.get("url") or p.get("pdf_url") or "").strip()`  
**Impact:** If paper has no web URL but has PDF, URL field contains PDF link (redundant with pdf_url field)

**Fix:** Keep url and pdf_url separate:
```python
url=p.get("url") or None,
pdf_url=p.get("pdf_url") or None,
```

---

### 10. [LOW] Redundant Redis Calls in Long-Poll
**File:** `tools/Literatur/slr.py:556, 582`  
**Bug:** `_get_orch_jobs_from_redis` called twice (line 556 for check, line 582 for response)  
**Impact:** Minor performance hit, 2x Redis roundtrips

**Fix:** Cache result from first call, reuse in response

---

## 📊 Summary

| Severity | Fixed | Pending |
|----------|-------|---------|
| CRITICAL | 3 | 1 |
| HIGH | 1 | 3 |
| MEDIUM | 0 | 3 |
| **Total** | **4** | **7** |

---

## 🚀 Recommended Fix Order

1. **CRITICAL #4**: Persist orch jobs to DB (prevents data loss)
2. **HIGH #5**: Fix Flask import (prevents items loss)
3. **HIGH #6**: Document field mapping (already working, just clarify)
4. **HIGH #7**: Fix long-poll condition (improve responsiveness)
5. **MEDIUM #8**: Increase save cap to 500
6. **MEDIUM #9**: Fix URL fallback
7. **LOW #10**: Optimize Redis calls

---

**Next Steps:**
1. Wait for subagent audit results (might find more bugs)
2. Apply CRITICAL #4 (DB persistence)
3. Apply HIGH #5 (Flask import)
4. Test end-to-end SLR flow
5. Deploy and monitor

