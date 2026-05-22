# Centralized Logging System - Quick Start Guide

## Overview
The PaperFull application now uses a centralized logging system with structured JSON logs, automatic rotation, and separate log files for different purposes.

## Log Files Location
```
backend/data/logs/logs/
├── app.log              # All application logs
├── error.log            # Errors only (30-day retention)
├── access.log           # HTTP requests
├── worker.log           # Background workers
└── perf.log             # Performance issues
```

## Quick Examples

### 1. Add Logging to Your Module

```python
import logging

# At the top of your module
log = logging.getLogger(__name__)

# Use throughout your code
log.info("Operation started")
log.warning("Potential issue detected")
log.error("Operation failed: %s", error_message)

# With structured data
log.info(
    "User action completed",
    extra={
        "user_id": user_id,
        "action": "create_paper",
        "duration_ms": 123.45
    }
)
```

### 2. View Logs in Real-Time

```bash
# All logs
tail -f backend/data/logs/logs/app.log | jq .

# Errors only
tail -f backend/data/logs/logs/error.log | jq .

# HTTP requests
tail -f backend/data/logs/logs/access.log | jq .

# Workers
tail -f backend/data/logs/logs/worker.log | jq .
```

### 3. Search Logs

```bash
# Find errors for a specific user
grep '"user_id": 123' backend/data/logs/logs/error.log | jq .

# Find slow requests (>1000ms)
jq 'select(.duration_ms > 1000)' backend/data/logs/logs/access.log

# Find all logs with specific request ID
grep '"req_id": "abc123"' backend/data/logs/logs/app.log | jq .
```

### 4. Log Levels

Set in `.env` file:
```bash
LOG_LEVEL=INFO  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
```

## Log Format

All logs are in JSON format:
```json
{
  "ts": "2026-05-23T01:05:12",
  "level": "INFO",
  "logger": "papergenerator.app",
  "msg": "Operation completed",
  "user_id": 123,
  "duration_ms": 456.78
}
```

## Best Practices

✅ **DO:**
- Use structured logging with `extra` parameter
- Use appropriate log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Include context (user_id, paper_id, etc.)
- Log exceptions with `log.exception()`

❌ **DON'T:**
- Log sensitive data (passwords, API keys, tokens)
- Use f-strings for structured data
- Log in tight loops (use sampling)
- Log PII without anonymization

## Common Patterns

### Error Handling
```python
try:
    result = risky_operation()
    log.info("Operation succeeded", extra={"result_id": result.id})
except Exception as e:
    log.exception("Operation failed", extra={"error": str(e)})
    raise
```

### Performance Monitoring
```python
import time

start = time.time()
result = expensive_operation()
duration = (time.time() - start) * 1000

if duration > 1000:
    log.warning(
        "Slow operation detected",
        extra={"operation": "expensive_op", "duration_ms": duration}
    )
```

### Worker Jobs
```python
log.info("Job started", extra={"job_id": job_id, "user_id": user_id})
try:
    process_job(job_id)
    log.info("Job completed", extra={"job_id": job_id})
except Exception as e:
    log.error("Job failed", extra={"job_id": job_id, "error": str(e)})
```

## Troubleshooting

**Logs not appearing?**
1. Check `LOG_LEVEL` in `.env`
2. Verify file permissions: `ls -l backend/data/logs/logs/`
3. Check disk space: `df -h`

**Need more detail?**
- Set `LOG_LEVEL=DEBUG` in `.env`
- Restart the application

**Too many logs?**
- Set `LOG_LEVEL=WARNING` or `ERROR`
- Reduce retention period in `observability_v2.py`

## More Information

See `LOGGING_IMPLEMENTATION.md` for complete documentation.
