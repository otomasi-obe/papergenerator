# Image Generation System - Bug Inventory & Analysis

**Audit Date**: 2026-05-22  
**System**: Gemini-based image generation with 4-worker pool  
**Components**: image_worker.py, image_jobs_bp.py, CreateImageGemini.py, compress.py

---

## Critical Bugs (P0)

### 1. Account Email Duplication
**Location**: `backend/.env:26,32`  
**Issue**: account1 and account4 both use `rofiqcp@gmail.com`
```
GEMINI_ACCOUNT1_EMAIL=rofiqcp@gmail.com
GEMINI_ACCOUNT4_EMAIL=rofiqcp@gmail.com
```
**Impact**: Same Google account logged in twice causes session conflicts. Google may invalidate one session when the other is active, leading to authentication failures.  
**Symptoms**: Random "not logged in" errors, cookie expiration, generation failures on specific workers.  
**Fix**: Use 4 distinct Google accounts, update .env and re-run GeminiCookies.py

---

### 2. Cookie Validation Incomplete
**Location**: `imageGenerator/GeminiCookies.py:288-289`
```python
if not _wait_for_required_cookies(page, timeout_s=90):
    print("  ! WARNING: PSIDTS belum muncul setelah 90s; cookies tetap disimpan...")
```
**Issue**: System continues with incomplete cookies (missing `__Secure-1PSIDTS`) instead of failing fast.  
**Impact**: Worker launches successfully but all generation requests fail with 401/redirect to login.  
**Symptoms**: Jobs stuck in 'running' state, browser redirects to login page, no image generated.  
**Fix**: Raise exception if required cookies are missing after timeout.

---

### 3. Image Intercept Timeout Mismatch
**Location**: `imageGenerator/CreateImageGemini.py:364-378`
```python
# Waits only 60s for image bytes
deadline = time.time() + 60
# But generation timeout is 240s
def generate_image(self, prompt: str, out_path: Path, *, generate_timeout_s: int = 240)
```
**Issue**: Download button appears after 240s, but intercept gives up after 60s.  
**Impact**: Complex images that take >60s to generate are lost even though generation succeeded.  
**Symptoms**: "Gagal capture image bytes (intercept timeout)" error despite download button visible.  
**Fix**: Increase intercept timeout to match `generate_timeout_s + 30`.

---

### 4. Browser Launch Failures Not Retried
**Location**: `image_worker.py:145`, `CreateImageGemini.py:244-281`
```python
acc.launch(pool._pw)  # No retry logic
```
**Issue**: Transient failures (port conflicts, profile locks, memory issues) cause permanent job failure.  
**Impact**: Jobs fail unnecessarily and must be manually resubmitted.  
**Symptoms**: "Failed to launch browser" errors, SingletonLock conflicts.  
**Fix**: Implement retry logic with exponential backoff (3 attempts, clean profile on 2nd failure).

---

### 5. Round-Robin State Not Thread-Safe
**Location**: `imageGenerator/CreateImageGemini.py:452-469`
```python
def _next_index(self) -> int:
    data = json.loads(self.state_path.read_text(encoding="utf-8"))
    # ... modify ...
    self.state_path.write_text(json.dumps({"next": nxt, ...}))
```
**Issue**: File-based state has race condition when multiple workers access simultaneously.  
**Impact**: Account rotation breaks, some accounts overused while others idle.  
**Symptoms**: Uneven load distribution, rate limit errors on specific accounts.  
**Fix**: Use database-backed counter with atomic increment, or per-worker assignment.

---

## High Priority Bugs (P1)

### 6. Headless Mode Detection Risk
**Location**: `CreateImageGemini.py:251`, `.env:24`
```python
headless = _env_bool("GEMINI_HEADLESS", True)  # Default True
# .env: GEMINI_HEADLESS=1
```
**Issue**: Gemini may detect headless Chrome and block image generation.  
**Impact**: All generations fail with "not available" or blank responses.  
**Symptoms**: Download button never appears, page shows error message.  
**Fix**: Use xvfb-run wrapper or set GEMINI_HEADLESS=0 and run on machine with display.

---

### 7. Compression Failure Silently Ignored
**Location**: `image_worker.py:148-152`
```python
try:
    compress_image(out_path, max_size_mb=1.0)
except Exception:
    log.warning("compress_image skipped for %s", out_path, exc_info=True)
```
**Issue**: Large images (>10MB) stored uncompressed, causing downstream issues.  
**Impact**: Image upload to frontend fails, page load slow, storage quota exceeded.  
**Symptoms**: Image generated but not displayed, "file too large" errors.  
**Fix**: Fail job if compression fails, or implement fallback (aggressive resize).

---

### 8. No Timeout on UI Element Waits
**Location**: `CreateImageGemini.py:151-177`
```python
def _open_image_tool(page) -> None:
    # No timeout on menu operations
    if not _click_via_js(page, ["Upload & alat", "Upload & tools"]):
        raise RuntimeError("Tidak bisa membuka menu 'Upload & alat'")
```
**Issue**: If UI doesn't load (network issue, Gemini redesign), worker hangs indefinitely.  
**Impact**: Worker thread blocked, no more jobs processed on that account.  
**Symptoms**: Jobs stuck in 'running' forever, worker unresponsive.  
**Fix**: Add timeout parameter to all UI operations (default 30s).

---

### 9. Worker Crash Loses Progress
**Location**: `image_worker.py:237-243`
```python
stale = ImageGenJob.query.filter(ImageGenJob.status.in_(['queued', 'running'])).all()
for j in stale:
    if j.status == 'running':
        j.status = 'queued'  # Restart from scratch
```
**Issue**: Job that was 99% complete restarts entirely after worker crash.  
**Impact**: Wasted compute, increased latency, user frustration.  
**Symptoms**: Same job takes 2x-3x longer after worker restart.  
**Fix**: Add checkpoint mechanism (save intermediate state) or accept loss for simplicity.

---

### 10. Error Messages Truncated
**Location**: `image_worker.py:201`
```python
job2.error = str(e)[:500]  # Truncated to 500 chars
```
**Issue**: Detailed error info (stack traces, Playwright errors) is lost.  
**Impact**: Debugging failures is difficult, root cause unclear.  
**Symptoms**: Generic "Error: ..." messages without context.  
**Fix**: Store full error in separate log file, reference in job.error field.

---

## Medium Priority Issues (P2)

### 11. No Rate Limit Tracking
**Issue**: Gemini likely has per-account rate limits (e.g., 10 images/hour).  
**Impact**: Account gets temporarily blocked, all jobs on that worker fail.  
**Fix**: Track requests per account per hour, pause worker when limit approached.

---

### 12. Browser Profile Corruption
**Issue**: If Chrome profile corrupted (bad cache, broken extensions), worker keeps failing.  
**Impact**: All jobs on that account fail until manual intervention.  
**Fix**: Detect repeated failures (3+ in a row), auto-delete profile and re-login.

---

### 13. No Job Priority System
**Issue**: All jobs are FIFO, no way to prioritize urgent requests.  
**Impact**: User waiting for one image must wait behind batch of 50 images.  
**Fix**: Add priority field to ImageGenJob, sort by (priority DESC, created_at ASC).

---

### 14. Worker Shutdown Not Graceful
**Location**: `image_worker.py:61-63`
```python
def stop(self):
    self._stop.set()
    self.q.put(None)  # Abrupt stop
```
**Issue**: Mid-generation jobs are killed, browser left in bad state.  
**Impact**: Orphaned Chrome processes, corrupted profiles.  
**Fix**: Set flag, wait for current job to finish (with timeout), then close.

---

### 15. Dispatcher Poll Interval Suboptimal
**Location**: `image_worker.py:212`
```python
def __init__(self, app, workers: list[_Worker], poll_interval: float = 1.5):
```
**Issue**: 1.5s adds unnecessary latency to job pickup.  
**Impact**: User waits extra 1.5s on average before generation starts.  
**Fix**: Reduce to 0.5s or use event-driven notification (DB trigger).

---

### 16. Model Documentation Incomplete
**Location**: `models.py:465`
```python
status = db.Column(db.String(20), nullable=False, default='queued')  
# Comment says: queued|running|done|error
# But code also uses 'cancelled'
```
**Issue**: Documentation doesn't match implementation.  
**Impact**: Developer confusion, potential bugs from assuming only 4 states.  
**Fix**: Update comment to include 'cancelled'.

---

### 17. Storage Path Error Messages Generic
**Location**: `image_worker.py:119-128`
```python
if paper_dir is None:
    job2.error = 'Invalid paper_id (path resolution failed)'
```
**Issue**: Doesn't distinguish between invalid paper_id vs. permission/disk issues.  
**Impact**: Hard to diagnose root cause of failures.  
**Fix**: Add more specific error messages (disk full, permission denied, etc.).

---

### 18. No Image Quality Validation
**Issue**: No check that generated image matches requirements (resolution, aspect ratio, content).  
**Impact**: User gets low-quality or wrong image, must regenerate.  
**Fix**: Add post-generation validation (min resolution, content safety check).

---

## Low Priority / Enhancements (P3)

### 19. Prompt Injection Risk
**Location**: `image_jobs_bp.py:37`
**Issue**: Prompt passed directly to Gemini without sanitization.  
**Impact**: Malicious prompts could try to manipulate Gemini (low risk, Gemini has own filters).  
**Fix**: Add content filtering or rate limit per user.

---

### 20. No Metrics/Observability
**Issue**: No tracking of success rate, average generation time, account health.  
**Impact**: Can't detect degradation or optimize performance.  
**Fix**: Add metrics collection (Prometheus, StatsD) for key events.

---

## Test Scenarios

### Scenario 1: Simple Image Generation
```bash
# Expected: Image generated in <60s, compressed to <1MB
curl -X POST /api/image-jobs \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"paper_id":"test123","prompt":"a red apple"}'
```
**Pass criteria**: Status transitions queued → running → done, image_id populated.

---

### Scenario 2: Complex Image (Long Generation)
```bash
# Expected: Image generated in <240s
curl -X POST /api/image-jobs \
  -d '{"paper_id":"test123","prompt":"detailed cyberpunk cityscape at sunset with flying cars and neon signs, photorealistic, 8k quality"}'
```
**Pass criteria**: No timeout error, image captured successfully.

---

### Scenario 3: Concurrent Requests
```bash
# Expected: 4 jobs run in parallel (one per account)
for i in {1..8}; do
  curl -X POST /api/image-jobs -d "{\"paper_id\":\"test123\",\"prompt\":\"image $i\"}" &
done
wait
```
**Pass criteria**: All 8 jobs complete, no double-dispatch, even account distribution.

---

### Scenario 4: Job Cancellation
```bash
JOB_ID=$(curl -X POST /api/image-jobs -d '{"paper_id":"test123","prompt":"test"}' | jq -r .id)
sleep 2
curl -X POST /api/image-jobs/$JOB_ID/cancel
```
**Pass criteria**: Job status becomes 'cancelled', no PaperImage created, file deleted.

---

### Scenario 5: Worker Restart
```bash
# Start job, kill worker mid-generation, restart
JOB_ID=$(curl -X POST /api/image-jobs -d '{"paper_id":"test123","prompt":"test"}' | jq -r .id)
sleep 10
pkill -f image_worker.py
python image_worker.py &
```
**Pass criteria**: Job demoted to 'queued', picked up again, completes successfully.

---

## Recommended Fixes Priority

1. **Immediate** (Deploy today):
   - Fix account email duplication (#1)
   - Fix cookie validation (#2)
   - Fix intercept timeout (#3)

2. **This Week**:
   - Add browser launch retry (#4)
   - Fix round-robin state (#5)
   - Verify headless mode works (#6)

3. **This Month**:
   - Fail on compression error (#7)
   - Add UI operation timeouts (#8)
   - Implement rate limit tracking (#11)

4. **Backlog**:
   - Job priority system (#13)
   - Graceful shutdown (#14)
   - Metrics/observability (#20)

---

## Account Management Improvements

### Current Issues:
- Account1 and Account4 share same email (session conflict)
- No health check per account
- No automatic cookie refresh
- No detection of rate limits

### Recommended Architecture:
```python
class AccountHealth:
    account_name: str
    last_success: datetime
    consecutive_failures: int
    requests_last_hour: int
    cookies_valid_until: datetime
    status: str  # healthy|degraded|blocked|invalid
    
    def should_use(self) -> bool:
        return (
            self.status == 'healthy' 
            and self.requests_last_hour < 10
            and self.cookies_valid_until > now()
        )
```

### Health Check Endpoint:
```python
@image_jobs_bp.route("/health", methods=["GET"])
@jwt_required()
def worker_health():
    # Return status of each worker/account
    return {
        "account1": {"status": "healthy", "queue_size": 2, "requests_last_hour": 5},
        "account2": {"status": "degraded", "queue_size": 0, "last_error": "..."},
        "account3": {"status": "blocked", "queue_size": 0, "reason": "rate limit"},
        "account4": {"status": "invalid", "queue_size": 0, "reason": "cookies expired"}
    }
```

---

## Error Handling Improvements

### Current: Generic Errors
```python
job.error = str(e)[:500]  # "RuntimeError: Gagal capture image bytes"
```

### Proposed: Structured Errors
```python
job.error_code = "IMAGE_INTERCEPT_TIMEOUT"
job.error_message = "Failed to capture image bytes after 60s"
job.error_details = json.dumps({
    "download_button_appeared": True,
    "intercept_attempts": 3,
    "redirect_urls": [...],
    "account": "account2"
})
job.retryable = True
```

### Error Categories:
- `AUTH_FAILED` - Cookie expired, need re-login (retryable after refresh)
- `RATE_LIMITED` - Account blocked temporarily (retryable after cooldown)
- `BROWSER_CRASH` - Chrome crashed (retryable on different account)
- `IMAGE_INTERCEPT_TIMEOUT` - Generated but not captured (retryable)
- `PROMPT_REJECTED` - Gemini refused prompt (not retryable)
- `STORAGE_FAILED` - Disk full or permission error (not retryable)

---

## Conclusion

**Total Bugs Found**: 20  
**Critical (P0)**: 5  
**High (P1)**: 5  
**Medium (P2)**: 7  
**Low (P3)**: 3  

**System Reliability**: 60% (estimated based on bug severity)  
**Main Bottlenecks**:
1. Account management (duplicate emails, no health checks)
2. Error handling (silent failures, poor diagnostics)
3. Browser automation (timeouts, intercept race conditions)

**Recommended Actions**:
1. Fix P0 bugs immediately (1-2 days)
2. Add comprehensive logging and metrics (1 week)
3. Implement account health monitoring (1 week)
4. Add integration tests for all scenarios (2 weeks)
