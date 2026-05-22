# Centralized Logging System Design
**PaperFull Application**  
**Version:** 1.0  
**Date:** 2026-05-22  
**Status:** Design Phase

---

## Executive Summary

This document outlines the design for a unified logging infrastructure across the PaperFull application (backend + frontend). The system addresses critical issues including lack of log rotation (359MB single file), scattered logging patterns, and absence of frontend error tracking.

**Key Objectives:**
- Implement log rotation with daily rollover and compression
- Standardize logging patterns across all modules
- Add frontend-to-backend error reporting
- Enhance performance monitoring and error categorization
- Maintain backward compatibility with existing logs
- Zero performance impact on production workloads

---

## 1. Current State Analysis

### 1.1 Backend Logging

**Existing Infrastructure:**
- ✅ Structured JSON logging via `observability.py`
- ✅ Request correlation with `req_id` (X-Request-ID)
- ✅ HTTP request logging (method, path, status, duration, IP, UA)
- ✅ Prometheus metrics integration
- ✅ Dual output: file (`app.log`) + stdout

**Current Log Locations:**
```
backend/
├── app.log                    # 359MB - NO ROTATION ⚠️ CRITICAL
└── log/
    └── <user_slug>/
        └── <paper_id>/
            ├── <chat_id>/     # Chat turn logs
            └── <job_id>/      # Generator job logs
```

**Issues Identified:**
1. **Critical:** `app.log` is 359MB with no rotation mechanism
2. **Code Quality:** 533+ logging statements, 43+ `print()` calls instead of proper logging
3. **Fragmentation:** User-specific logs scattered across subdirectories (6.9MB total)
4. **Limited Context:** No user_id, paper_id in main app.log entries
5. **No Error Categorization:** All errors logged generically
6. **Limited Performance Tracking:** Only HTTP request duration tracked

**Current Log Format (JSON):**
```json
{
  "ts": "2026-05-20T20:46:20",
  "level": "INFO",
  "logger": "papergenerator.obs",
  "msg": "http",
  "req_id": "318158f72a0e4693",
  "method": "GET",
  "path": "/api/auth/google/callback",
  "endpoint": "auth.google_callback",
  "status": 302,
  "duration_ms": 32.89,
  "ip": "54.86.66.252",
  "ua": "Mozilla/5.0..."
}
```

### 1.2 Frontend Logging

**Current State:**
- Only 18 `console.warn()` / `console.error()` statements
- No centralized logging service
- No error reporting to backend
- No user context in logs
- No performance tracking

**Locations:**
- `stores/user.js` - 1 warning
- `stores/paperJobs.js` - 6 warnings
- `components/LiteratureTab.vue` - 2 logs
- `components/RevisiProposalCard.vue` - 1 warning
- `views/AdminPage.vue` - 3 errors
- `views/FilesPage.vue` - 1 error
- `views/DashboardPage.vue` - 3 errors

---

## 2. Architecture Design

### 2.1 System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Vue.js)                       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Logger Service (utils/logger.js)                      │ │
│  │  - Local console output                                │ │
│  │  - Buffer & batch errors to backend                    │ │
│  │  - User context injection                              │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │ POST /api/logs/frontend
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend (Flask)                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Centralized Logger (backend/logger.py)                │ │
│  │  - Context injection (user_id, paper_id, req_id)       │ │
│  │  - Error categorization                                │ │
│  │  - Performance tracking                                │ │
│  └────────────────────────────────────────────────────────┘ │
│                           │                                  │
│  ┌────────────────────────┼────────────────────────────────┐│
│  │  Log Handlers          │                                ││
│  │  ┌─────────────────────▼──────────────────┐            ││
│  │  │ RotatingFileHandler (app.log)          │            ││
│  │  │ - Daily rotation                       │            ││
│  │  │ - 7 days retention                     │            ││
│  │  │ - gzip compression                     │            ││
│  │  └────────────────────────────────────────┘            ││
│  │  ┌────────────────────────────────────────┐            ││
│  │  │ StreamHandler (stdout)                 │            ││
│  │  │ - For Docker/systemd log collection    │            ││
│  │  └────────────────────────────────────────┘            ││
│  │  ┌────────────────────────────────────────┐            ││
│  │  │ ErrorFileHandler (errors.log)          │            ││
│  │  │ - ERROR/CRITICAL only                  │            ││
│  │  │ - 30 days retention                    │            ││
│  │  └────────────────────────────────────────┘            ││
│  │  ┌────────────────────────────────────────┐            ││
│  │  │ PerformanceFileHandler (perf.log)      │            ││
│  │  │ - Slow queries, API calls              │            ││
│  │  │ - 7 days retention                     │            ││
│  │  └────────────────────────────────────────┘            ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Log Storage                               │
│  backend/logs/                                               │
│  ├── app.log                    # Current day                │
│  ├── app.log.2026-05-21.gz      # Previous days (compressed) │
│  ├── app.log.2026-05-20.gz                                   │
│  ├── errors.log                 # Current errors             │
│  ├── errors.log.2026-05-21.gz                                │
│  ├── perf.log                   # Performance logs           │
│  └── user_logs/                 # Per-user logs (existing)   │
│      └── <user_slug>/<paper_id>/<job_id>/                    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Log Levels & Categories

**Standard Levels:**
- `DEBUG` - Development/troubleshooting (not in production)
- `INFO` - Normal operations, business events
- `WARNING` - Recoverable issues, degraded performance
- `ERROR` - Operation failures, caught exceptions
- `CRITICAL` - System failures, data corruption

**Custom Categories (via logger name):**
- `papergenerator.http` - HTTP request/response
- `papergenerator.auth` - Authentication/authorization
- `papergenerator.db` - Database operations
- `papergenerator.ai` - AI generation jobs
- `papergenerator.chat` - Chat operations
- `papergenerator.files` - File uploads/processing
- `papergenerator.perf` - Performance metrics
- `papergenerator.security` - Security events
- `papergenerator.frontend` - Frontend errors

### 2.3 Log Format Specification

**Standard Fields (all logs):**
```json
{
  "ts": "2026-05-22T23:06:46+07:00",
  "level": "INFO",
  "logger": "papergenerator.http",
  "msg": "Request completed",
  "req_id": "a1b2c3d4e5f6",
  "user_id": 123,
  "paper_id": "abc123",
  "session_id": "sess_xyz"
}
```

**HTTP Request Logs:**
```json
{
  "ts": "2026-05-22T23:06:46+07:00",
  "level": "INFO",
  "logger": "papergenerator.http",
  "msg": "http",
  "req_id": "a1b2c3d4e5f6",
  "method": "POST",
  "path": "/api/chat/send",
  "endpoint": "chat.send_message",
  "status": 200,
  "duration_ms": 1234.56,
  "ip": "192.168.1.1",
  "ua": "Mozilla/5.0...",
  "user_id": 123,
  "paper_id": "abc123"
}
```

**Error Logs:**
```json
{
  "ts": "2026-05-22T23:06:46+07:00",
  "level": "ERROR",
  "logger": "papergenerator.ai",
  "msg": "Paper generation failed",
  "req_id": "a1b2c3d4e5f6",
  "user_id": 123,
  "paper_id": "abc123",
  "job_id": "job_xyz",
  "error_type": "APIError",
  "error_code": "RATE_LIMIT",
  "exc": "Traceback...",
  "context": {
    "model": "V-OPUS",
    "stage": "introduction",
    "retry_count": 3
  }
}
```

**Performance Logs:**
```json
{
  "ts": "2026-05-22T23:06:46+07:00",
  "level": "WARNING",
  "logger": "papergenerator.perf",
  "msg": "Slow database query",
  "req_id": "a1b2c3d4e5f6",
  "user_id": 123,
  "operation": "fetch_papers",
  "duration_ms": 5432.10,
  "threshold_ms": 1000,
  "query": "SELECT * FROM papers WHERE..."
}
```

**Frontend Error Logs:**
```json
{
  "ts": "2026-05-22T23:06:46+07:00",
  "level": "ERROR",
  "logger": "papergenerator.frontend",
  "msg": "Upload failed",
  "user_id": 123,
  "paper_id": "abc123",
  "error_type": "NetworkError",
  "url": "/api/papers/abc123/files",
  "browser": "Chrome 148.0.0.0",
  "os": "Linux",
  "viewport": "1920x1080",
  "stack": "Error: Network request failed\n  at..."
}
```

---

## 3. Implementation Components

### 3.1 Backend Logger Module

**File:** `backend/logger.py`

**Features:**
- Centralized logger factory with context injection
- Automatic user_id/paper_id extraction from Flask context
- Error categorization helpers
- Performance tracking decorators
- Log rotation configuration

**API:**
```python
from logger import get_logger, log_performance, log_error

# Get logger with automatic context
log = get_logger(__name__)

# Automatic context injection
log.info("User logged in")  # Includes user_id, req_id automatically

# Performance tracking
@log_performance(threshold_ms=1000)
def slow_operation():
    pass

# Error categorization
log_error("API call failed", error_type="APIError", error_code="TIMEOUT")
```

### 3.2 Frontend Logger Service

**File:** `frontend/src/utils/logger.js`

**Features:**
- Unified logging API (replaces console.log/warn/error)
- Automatic user context injection
- Error batching and backend reporting
- Local console output (development)
- Performance tracking (page load, API calls)

**API:**
```javascript
import logger from '@/utils/logger'

// Basic logging
logger.info('Paper created', { paperId: 'abc123' })
logger.warn('Slow response', { duration: 5000 })
logger.error('Upload failed', { error: e })

// Performance tracking
logger.trackPageLoad()
logger.trackApiCall('/api/papers', 1234)

// Error reporting (auto-sends to backend)
logger.reportError(error, { context: 'file-upload' })
```

### 3.3 Log Rotation Configuration

**Strategy:**
- **app.log:** Daily rotation, 7 days retention, gzip compression
- **errors.log:** Daily rotation, 30 days retention, gzip compression
- **perf.log:** Daily rotation, 7 days retention, gzip compression
- **User logs:** No rotation (already small, per-job files)

**Implementation:** Python's `logging.handlers.TimedRotatingFileHandler`

**Disk Usage Estimate:**
- Current: 359MB (unrotated)
- With rotation: ~50MB active + ~200MB compressed archives = 250MB total
- Savings: ~100MB + prevents unbounded growth

### 3.4 Context Injection Middleware

**File:** `backend/context_middleware.py`

**Features:**
- Extract user_id from JWT token
- Extract paper_id from request path/body
- Inject into Flask `g` object
- Automatic propagation to all log calls

**Integration:**
```python
@app.before_request
def inject_log_context():
    g.log_context = {
        'req_id': g._req_id,
        'user_id': get_jwt_identity() if has_jwt() else None,
        'paper_id': extract_paper_id_from_request(),
    }
```

### 3.5 Error Categorization System

**Error Types:**
- `AuthError` - Authentication/authorization failures
- `ValidationError` - Input validation failures
- `DatabaseError` - Database operation failures
- `APIError` - External API call failures
- `FileError` - File upload/processing failures
- `AIError` - AI generation failures
- `NetworkError` - Network/connectivity issues
- `UnknownError` - Uncategorized errors

**Error Codes:**
- `RATE_LIMIT` - Rate limit exceeded
- `TIMEOUT` - Operation timeout
- `NOT_FOUND` - Resource not found
- `PERMISSION_DENIED` - Insufficient permissions
- `INVALID_INPUT` - Invalid request data
- `QUOTA_EXCEEDED` - User quota exceeded
- `SERVICE_UNAVAILABLE` - External service down

### 3.6 Performance Monitoring

**Tracked Metrics:**
- HTTP request duration (existing)
- Database query duration (new)
- AI generation duration (existing, enhance)
- File processing duration (new)
- Frontend page load time (new)
- Frontend API call duration (new)

**Thresholds:**
- HTTP requests: >1000ms = WARNING
- Database queries: >500ms = WARNING
- AI generation: >120s = WARNING
- File processing: >5000ms = WARNING

---

## 4. Migration Plan

### Phase 1: Log Rotation (Week 1) - CRITICAL

**Priority:** P0 (Critical - prevents disk full)

**Steps:**
1. Backup current `app.log` (359MB)
2. Update `observability.py` to use `TimedRotatingFileHandler`
3. Configure daily rotation with 7-day retention
4. Add compression for archived logs
5. Test rotation mechanism
6. Deploy to production

**Risk:** Low - backward compatible, no API changes

### Phase 2: Backend Logger Module (Week 1-2)

**Priority:** P1 (High)

**Steps:**
1. Create `backend/logger.py` with centralized logger factory
2. Add context injection middleware
3. Update `observability.py` to use new logger
4. Migrate 5-10 high-traffic modules (app.py, chat.py, auth.py)
5. Replace `print()` statements with proper logging
6. Test in staging environment
7. Deploy to production

**Risk:** Medium - requires code changes across modules

### Phase 3: Frontend Logger Service (Week 2-3)

**Priority:** P1 (High)

**Steps:**
1. Create `frontend/src/utils/logger.js`
2. Add backend endpoint `/api/logs/frontend`
3. Implement error batching and reporting
4. Migrate existing `console.warn/error` calls
5. Add performance tracking
6. Test in development
7. Deploy to production

**Risk:** Low - additive, doesn't break existing code

### Phase 4: Error Categorization (Week 3-4)

**Priority:** P2 (Medium)

**Steps:**
1. Define error taxonomy (types + codes)
2. Add error categorization helpers to logger
3. Update error handling across modules
4. Add error aggregation queries
5. Create error dashboard (optional)

**Risk:** Low - enhances existing error logging

### Phase 5: Performance Monitoring (Week 4-5)

**Priority:** P2 (Medium)

**Steps:**
1. Add database query duration tracking
2. Add file processing duration tracking
3. Add frontend performance tracking
4. Create performance dashboard (optional)
5. Set up alerts for slow operations

**Risk:** Low - additive monitoring

### Phase 6: Cleanup & Documentation (Week 5-6)

**Priority:** P3 (Low)

**Steps:**
1. Remove remaining `print()` statements
2. Standardize logger names across modules
3. Document logging best practices
4. Create log analysis scripts
5. Train team on new logging system

**Risk:** None - cleanup only

---

## 5. Code Structure

### 5.1 Backend Structure

```
backend/
├── logger.py                    # NEW: Centralized logger module
├── context_middleware.py        # NEW: Context injection
├── observability.py             # UPDATED: Add rotation
├── logs/                        # NEW: Organized log directory
│   ├── app.log
│   ├── app.log.2026-05-21.gz
│   ├── errors.log
│   ├── perf.log
│   └── user_logs/              # Existing user logs
│       └── <user_slug>/...
└── log_analysis/               # NEW: Analysis scripts
    ├── error_summary.py
    ├── perf_report.py
    └── user_activity.py
```

### 5.2 Frontend Structure

```
frontend/src/
├── utils/
│   └── logger.js               # NEW: Frontend logger service
└── api/
    └── logs.js                 # NEW: Log reporting API
```

---

## 6. Configuration Examples

### 6.1 Logger Configuration

**File:** `backend/logger.py`

```python
import logging
from logging.handlers import TimedRotatingFileHandler
import gzip
import shutil
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

def namer(default_name):
    """Add .gz extension to rotated logs."""
    return default_name + ".gz"

def rotator(source, dest):
    """Compress rotated logs."""
    with open(source, 'rb') as f_in:
        with gzip.open(dest, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    Path(source).unlink()

def setup_rotating_handler(filename, level=logging.INFO, when='midnight', 
                          backup_count=7):
    """Create a rotating file handler with compression."""
    handler = TimedRotatingFileHandler(
        LOG_DIR / filename,
        when=when,
        interval=1,
        backupCount=backup_count,
        encoding='utf-8',
        utc=True
    )
    handler.namer = namer
    handler.rotator = rotator
    handler.setLevel(level)
    return handler
```

### 6.2 Frontend Logger Configuration

**File:** `frontend/src/utils/logger.js`

```javascript
class Logger {
  constructor() {
    this.buffer = []
    this.flushInterval = 10000 // 10 seconds
    this.maxBufferSize = 50
    this.startAutoFlush()
  }

  log(level, message, context = {}) {
    const entry = {
      ts: new Date().toISOString(),
      level,
      msg: message,
      user_id: this.getUserId(),
      paper_id: this.getPaperId(),
      ...context
    }

    // Console output (development)
    if (import.meta.env.DEV) {
      console[level.toLowerCase()](message, context)
    }

    // Buffer for backend (errors only in production)
    if (level === 'ERROR' || level === 'CRITICAL') {
      this.buffer.push(entry)
      if (this.buffer.length >= this.maxBufferSize) {
        this.flush()
      }
    }
  }

  async flush() {
    if (this.buffer.length === 0) return
    
    const logs = [...this.buffer]
    this.buffer = []

    try {
      await fetch('/api/logs/frontend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ logs })
      })
    } catch (e) {
      console.error('Failed to send logs to backend', e)
    }
  }

  info(msg, ctx) { this.log('INFO', msg, ctx) }
  warn(msg, ctx) { this.log('WARNING', msg, ctx) }
  error(msg, ctx) { this.log('ERROR', msg, ctx) }
}

export default new Logger()
```

---

## 7. Monitoring & Maintenance

### 7.1 Log Analysis Scripts

**Error Summary:**
```bash
# Top 10 errors in last 24 hours
python backend/log_analysis/error_summary.py --last 24h

# Errors by user
python backend/log_analysis/error_summary.py --by-user

# Errors by endpoint
python backend/log_analysis/error_summary.py --by-endpoint
```

**Performance Report:**
```bash
# Slow queries in last hour
python backend/log_analysis/perf_report.py --slow-queries --last 1h

# API endpoint performance
python backend/log_analysis/perf_report.py --endpoints --last 24h
```

### 7.2 Disk Usage Monitoring

**Automated Cleanup:**
```bash
# Cron job: daily at 2 AM
0 2 * * * find /home/sirobo/papergenerator/backend/logs -name "*.gz" -mtime +30 -delete
```

**Disk Usage Alert:**
```bash
# Alert if logs directory > 500MB
du -sm /home/sirobo/papergenerator/backend/logs | awk '$1 > 500 {print "WARNING: Logs directory exceeds 500MB"}'
```

### 7.3 Prometheus Metrics

**New Metrics:**
```python
LOG_ERRORS_TOTAL = Counter(
    "log_errors_total",
    "Total errors logged by category",
    ["error_type", "error_code"]
)

SLOW_OPERATIONS_TOTAL = Counter(
    "slow_operations_total",
    "Operations exceeding performance threshold",
    ["operation", "threshold_ms"]
)

FRONTEND_ERRORS_TOTAL = Counter(
    "frontend_errors_total",
    "Frontend errors reported to backend",
    ["error_type", "page"]
)
```

---

## 8. Success Metrics

### 8.1 Technical Metrics

- ✅ Log file size < 100MB (current: 359MB)
- ✅ Log rotation working (daily, compressed)
- ✅ Zero `print()` statements in production code
- ✅ 100% of errors categorized
- ✅ Frontend error reporting rate > 90%
- ✅ Performance tracking coverage > 80%

### 8.2 Operational Metrics

- ✅ Mean time to detect (MTTD) errors < 5 minutes
- ✅ Mean time to resolve (MTTR) errors < 2 hours
- ✅ Log query performance < 1 second
- ✅ Disk usage growth < 10MB/day

---

## 9. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Log rotation fails | High | Low | Test thoroughly, monitor disk usage |
| Performance overhead | Medium | Low | Use async logging, batch writes |
| Disk space exhaustion | High | Low | Automated cleanup, monitoring |
| Breaking existing code | Medium | Medium | Gradual migration, backward compatibility |
| Frontend log spam | Low | Medium | Rate limiting, client-side filtering |

---

## 10. Next Steps

### Immediate Actions (This Week)

1. **CRITICAL:** Implement log rotation for `app.log` (359MB → managed)
2. Create `backend/logger.py` module
3. Update `observability.py` with rotation handlers
4. Test rotation in staging environment

### Short-term (Next 2 Weeks)

1. Migrate high-traffic modules to new logger
2. Create frontend logger service
3. Add backend endpoint for frontend logs
4. Replace `print()` statements

### Long-term (Next Month)

1. Implement error categorization
2. Add performance monitoring
3. Create log analysis scripts
4. Build monitoring dashboard (optional)

---

## Appendix A: Log Retention Policy

| Log Type | Retention | Compression | Size Estimate |
|----------|-----------|-------------|---------------|
| app.log | 7 days | gzip | ~50MB active + ~150MB archived |
| errors.log | 30 days | gzip | ~20MB active + ~50MB archived |
| perf.log | 7 days | gzip | ~10MB active + ~30MB archived |
| user_logs | 90 days | none | ~10MB (grows slowly) |

**Total Estimated Disk Usage:** ~320MB (vs 359MB+ unmanaged growth)

---

## Appendix B: Example Log Queries

**Find all errors for a specific user:**
```bash
grep '"user_id": 123' backend/logs/errors.log | jq .
```

**Find slow API calls:**
```bash
grep '"duration_ms"' backend/logs/app.log | jq 'select(.duration_ms > 1000)'
```

**Count errors by type:**
```bash
grep '"level": "ERROR"' backend/logs/errors.log | jq -r .error_type | sort | uniq -c
```

**Frontend errors in last hour:**
```bash
grep '"logger": "papergenerator.frontend"' backend/logs/app.log | \
  jq 'select(.ts > "'$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S)'")'
```

---

**Document Status:** Ready for Review  
**Next Review Date:** 2026-06-01  
**Owner:** Backend Team  
**Stakeholders:** DevOps, Frontend Team, QA
