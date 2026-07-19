# HANDOFF: PaperFull Generate Full - Elite E2E Fix

**Session Date:** 2026-07-19
**Project:** PaperFull (papergenerator)
**Profile:** viola_otomasi
**User:** zonkedbil@gmail.com (elite badge)

---

## Current State (Verified Working)

| Component | Status | Details |
|-----------|--------|---------|
| **API Server** | ✅ Healthy | Flask/gunicorn on `localhost:8001` |
| **Image Worker** | ✅ Running | PM2 `paper-image-worker` — 7 workers (elite=3, pro=2, starter=1, trial=1) |
| **Web Auth** | ✅ Working | zonkedbil@gmail.com / testpassword123 → JWT cookie |
| **Editor UI** | ✅ Accessible | https://paperfull.app/editor loads after login |
| **Browser** | ✅ Ready | Already at editor page, logged in as elite |
| **Badge Resolution** | ✅ Working | 23 queued jobs with `badge=elite`, 2 with `badge=trial` |
| **TierDispatcher Architecture** | ✅ Deployed | Priority queue per tier, FIFO within priority |
| **DB Schema** | ✅ Migrated | `priority` column + composite index `(priority DESC, created_at ASC)` on `image_gen_jobs` |

---

## 3 Critical Blockers (Must Fix Before Generate Full Works)

### 1. Priority Bug — Elite Jobs Starved
**File:** `backend/tools/paperfull/jobs.py` line ~3373
**Issue:** `user_priority` set once at line 2169, but `user_badge` re-queried at line 3369-3373 **without updating `user_priority`**.
**Result:** All elite jobs created with `priority=0` instead of `3` → sit behind trial/pro in queue.

### 2. GPT-Image Disabled for Elite
**File:** `backend/config/badge_tiers.py` line 173
**Issue:** `cx/gpt-5.5-image` commented out in `get_image_models()` for elite tier.
**Result:** Elite falls back to Cloudflare free models → 429 quota exhausted → infinite re-queue.

### 3. Missing API Keys
**File:** `backend/.env`
**Missing:** `NINEROUTER_API_KEY`, `IMAGE_API_KEY`
**Result:** All image generation providers fail (no auth).

---

## Fix Commands (Run in Order)

```bash
cd /home/sirobo/papergenerator/backend

# 1. Fix priority bug — add missing user_priority update after badge re-query
sed -i '3373a\                    user_priority = TIER_RANK.get(user_badge, 0)' tools/paperfull/jobs.py

# 2. Enable GPT-Image for elite tier
sed -i 's/# "cx\/gpt-5.5-image"/"cx\/gpt-5.5-image"/' config/badge_tiers.py

# 3. Add API keys to .env (replace *** with actual values from vault/secrets)
echo 'NINEROUTER_API_KEY=***' >> .env
echo 'IMAGE_API_KEY=***' >> .env

# 4. Restart services
pm2 restart paper-backend-flask paper-image-worker
```

---

## Expected End-to-End Flow After Fix

1. **Open editor** (already loaded at https://paperfull.app/editor)
2. **Click "Generate Full"** → SSE stream starts
3. **Paper generation** → `event: content` tokens
4. **Figure enqueue** → `event: progress {stage: "image_generation", ...}` with `badge=elite, priority=3`
5. **3 parallel elite workers** pick up jobs → call **GPT-Image (cx/gpt-5.5-image)**
6. **Auto-embed to figures** → Frontend receives `imageUrl` via SSE → updates figure `imageUrl` in real-time
7. **No manual refresh needed** — frontend already subscribes to `/api/papers/:id/ai-jobs/active` SSE

---

## Key Files Modified This Session

| File | Change |
|------|--------|
| `backend/tools/image_generation/worker.py` | **Rewritten** — TierDispatcher + TierWorker pool (elite=3, pro=2, starter=1, trial=1), priority queue, `submit_now(badge)` |
| `backend/tools/paperfull/paper_worker.py` | `_auto_enqueue_figure_images()` sets `badge` + `priority`; `submit_now` passes badge |
| `backend/tools/paperfull/jobs.py` | `generate_stream` (3 sites), `generate_figures_background` set `badge` + `priority`; `submit_now` passes badge |
| `backend/tools/image_generation/image_jobs.py` | `create_image_job` sets `badge` + `priority`; `submit_now` passes badge |
| `backend/utils/database/models.py` | Added `priority` column to `ImageGenJob`, updated `to_dict()` |
| `backend/config/badge_tiers.py` | Reference — `TIER_RANK`, `get_max_parallel_jobs`, `get_image_models` |

---

## DB Migration Applied (Raw SQL)

```sql
ALTER TABLE image_gen_jobs ADD COLUMN priority INTEGER DEFAULT 0;
CREATE INDEX ix_image_gen_jobs_priority ON image_gen_jobs (priority DESC, created_at ASC);
```

---

## Verification Commands (Post-Fix)

```bash
# Check worker pool startup
pm2 logs paper-image-worker --lines 20 | grep "worker pool started"

# Verify elite jobs have priority=3
.venv/bin/python -c "
from utils.database.models import ImageGenJob, db
from main import app
with app.app_context():
    jobs = ImageGenJob.query.filter_by(status='queued', badge='elite').all()
    for j in jobs: print(f'{j.id} priority={j.priority}')
"

# Test generate full via API
curl -X POST http://localhost:8001/api/papers/<paper_id>/generate-stream \
  -H "Content-Type: application/json" \
  -d '{"prompt":"test","generate_images":true}' \
  --cookie-jar - --cookie cookies.txt
```

---

## Notes for Next Session

- **Browser session** may need re-login (cookies expire)
- **PM2 processes** persist across sessions: `pm2 list` to verify
- **API keys** must be obtained from vault/secrets manager — not in repo
- **Frontend cache:** After deploy, users must hard refresh `Ctrl+Shift+R` (static assets cached 1y immutable)

---

## Auto-Embed Implementation (Already Done)

**Frontend:** `src/components/editor/EditorPage.vue` → subscribes to SSE `/api/papers/:id/ai-jobs/active`
**On `image_generation` event:** Updates `figure.imageUrl` in reactive state → re-renders figure preview instantly
**No user action required** — works automatically once worker completes GPT-Image generation.