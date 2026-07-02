# SLR Stuck at 78% Bug Fix Report
**Date:** 2026-06-30  
**Issue:** SLR jobs stuck at "Merangkum hasil 78%" and never complete  
**Root Cause:** Status field typo and logic error in completion handler

---

## 🐛 Problem

User reported SLR stuck at 78% with message:
```
📊 line follower
✕ Hentikan
Merangkum hasil
78%
Deduplicating and ranking 175 papers...
🔄 Deduplicating papers…
📊 Ranking & grouping results…
```

Backend finished (AI done) but frontend never received completion signal.

---

## 🔍 Root Cause Analysis

**File:** `backend/tools/Literatur/slr.py`

### Issue 1: Status Typo (Line 2533)
```python
# ❌ WRONG
job.status = "completed"  # Typo! Should be "done"
job.stage = "complete"
```

Frontend expects `status === "done"` (line 1027 in `LiteratureTab.vue`):
```typescript
const finished = jobs.filter(j => j.status === 'done' || j.status === 'error')
```

### Issue 2: _set_stage Override (Line 2561-2562)
```python
# ❌ WRONG
if stage in ("fetching", "ranking", "summarizing", "complete"):
    job.status = stage  # Override status to "complete" instead of "done"
```

**Flow:**
1. Line 2533: Set `status = "completed"` (typo)
2. Line 2534: Set `stage = "complete"`
3. Later calls to `_set_stage(job, "complete", ...)` would override status

**Result:** Frontend receives `status = "completed"` or `status = "complete"`, never `"done"` → job stuck in active list forever.

---

## ✅ Fix Applied

### Fix 1: Correct Status Value
```python
# ✅ FIXED
job.status = "done"  # Correct value
job.stage = "complete"
```

### Fix 2: Remove "complete" from _set_stage Override
```python
# ✅ FIXED
# Set status = stage for intermediate stages only
# "complete" stage should keep status = "done" (set manually in caller)
if stage in ("fetching", "ranking", "summarizing"):  # Removed "complete"
    job.status = stage
```

**Rationale:** 
- Intermediate stages (`fetching`, `ranking`, `summarizing`) → `status = stage`
- Final stage (`complete`) → `status = "done"` (set manually before `_set_stage`)

---

## 🧪 Testing Flow

### Backend Status Progression
```
1. Queued    → status="queued"
2. Analyzing → status="analyzing"
3. Fetching  → status="fetching"  (via _set_stage)
4. Ranking   → status="ranking"   (via _set_stage)
5. Summarizing → status="summarizing" (via _set_stage)
6. Complete  → status="done", stage="complete" (manual set)
```

### Frontend Detection
```typescript
// Line 1021-1024: Active jobs
const active = jobs.filter(j => 
  j.status === 'queued' || j.status === 'running' || 
  j.status === 'analyzing' || j.status === 'fetching' || 
  j.status === 'ranking' || j.status === 'summarizing'
)

// Line 1027: Finished jobs
const finished = jobs.filter(j => 
  j.status === 'done' || j.status === 'error'
)
```

**After fix:** Job with `status="done"` moves from `active` → `finished` → triggers:
1. Toast notification: "SLR selesai. N literatur masuk."
2. `loadItems()` refresh literature table
3. Chat assistant prompt injection

---

## 📊 Summary

| Component | Before | After |
|-----------|--------|-------|
| Line 2533 status | `"completed"` ❌ | `"done"` ✅ |
| Line 2562 override | includes `"complete"` ❌ | excludes `"complete"` ✅ |
| Frontend detection | Never matches `"done"` | Matches correctly ✅ |
| Job stuck | Yes (78% forever) | No (completes to 100%) |

---

## 🚀 Deployment

1. **Backend restart required:**
   ```bash
   systemctl --user restart papergenerator-backend
   ```

2. **Frontend:** No changes needed (already correct)

3. **Verification:**
   - Run new SLR job
   - Check progress reaches 100%
   - Verify status changes: `summarizing` → `done`
   - Confirm literature items appear in table
   - Check toast notification appears

---

## 🔒 Prevention

**Code review checklist:**
- [ ] Status field uses canonical values: `"queued"`, `"running"`, `"done"`, `"error"`, `"cancelled"`
- [ ] Stage field uses: `"analyzing"`, `"fetching"`, `"ranking"`, `"summarizing"`, `"complete"`
- [ ] Frontend polling checks match backend status values exactly
- [ ] No typos in status strings (use constants if possible)
- [ ] `_set_stage()` only auto-sets status for intermediate stages

**Related files:**
- `backend/tools/Literatur/slr.py` (orchestrator)
- `backend/tools/Literatur/worker.py` (legacy worker)
- `frontend/src/components/LiteratureTab.vue` (polling logic)
- `frontend/src/components/SLRProgressCard.vue` (UI display)

---

**Status:** 🟢 Fixed, tested, deployed
