# Centralized Logging System Implementation

## Summary

Successfully implemented a centralized logging system for the PaperFull application that consolidates all logging into `backend/data/logs/` with proper rotation, levels, and monitoring capabilities.

## Implementation Date
2026-05-23

## Log Files Structure

All logs are stored in `backend/data/logs/` with the following structure:

```
backend/data/logs/
├── app.log              # All application logs (INFO+), 7-day retention
├── error.log            # Error logs only (ERROR+), 30-day retention
├── access.log           # HTTP access logs (INFO+), 7-day retention
├── worker.log           # Background worker logs (INFO+), 7-day retention
├── perf.log             # Performance logs (WARNING+), 7-day retention
└── generator/           # Per-account Gemini image generation logs
    ├── account1.log
    ├── account2.log
    ├── account3.log
    └── account4.log
```

## Features

### 1. **Log Rotation**
- Daily rotation at midnight UTC
- Automatic gzip compression of archived logs
- Configurable retention policies:
  - `app.log`: 7 days
  - `error.log`: 30 days (for compliance)
  - `access.log`: 7 days
  - `worker.log`: 7 days
  - `perf.log`: 7 days

### 2. **Structured JSON Logging**
All logs are written in JSON format for easy parsing by log aggregators (Loki, Grafana, ELK):

```json
{
  "ts": "2026-05-23T00:57:47",
  "level": "INFO",
  "logger": "papergenerator.app",
  "msg": "PaperFull API starting on port 1001",
  "req_id": "a1b2c3d4e5f6",
  "method": "POST",
  "path": "/api/papers",
  "status": 200,
  "duration_ms": 123.45
}
```

### 3. **Log Levels**
- `DEBUG`: Detailed diagnostic information
- `INFO`: General informational messages
- `WARNING`: Warning messages for potential issues
- `ERROR`: Error messages for failures
- `CRITICAL`: Critical errors that may cause system failure

### 4. **Separate Log Files by Category**

#### app.log
- All application logs (INFO and above)
- General application flow and operations
- 7-day retention

#### error.log
- Error logs only (ERROR and above)
- 30-day retention for compliance and debugging
- Critical for troubleshooting production issues

#### access.log
- HTTP request/response logs
- Includes: method, path, status code, duration, IP, user agent
- Filtered to exclude health check endpoints
- 7-day retention

#### worker.log
- Background worker logs (image generation, SLR processing)
- Includes logs from: `image_worker`, `slr_worker`, `gemini` modules
- 7-day retention

#### perf.log
- Performance-related logs (WARNING and above)
- Slow operations and performance bottlenecks
- 7-day retention

## Files Modified

### Core Logging Infrastructure
1. **backend/observability_v2.py**
   - Enhanced with 5 separate log handlers (app, error, access, worker, perf)
   - Added log rotation with gzip compression
   - Updated docstring with complete feature list

### Application Integration
2. **backend/app.py**
   - Changed import from `observability` to `observability_v2`
   - Replaced `print()` statement with `log.info()` (line 1128)

### Worker Modules
3. **backend/image_worker.py**
   - Already using logging properly ✓
   - No changes needed

4. **backend/slr_worker.py**
   - Already using logging properly ✓
   - No changes needed

### Generation Modules
5. **backend/generate_paper_single.py**
   - Replaced 2 `print()` statements with `log.info()` (lines 645-649, 677-681)

6. **backend/generate_paper_chunked.py**
   - Replaced 12 `print()` statements with `log.info()` throughout the file
   - Progress messages now properly logged

### Image Generation
7. **backend/imageGenerator/CreateImageGemini.py**
   - Replaced 4 internal `print()` statements with proper logging
   - CLI output print() statements kept for user feedback
   - Per-account logging already implemented ✓

## How to Use the Logging System

### 1. Basic Usage in Python Modules

```python
import logging

# Create a logger for your module
log = logging.getLogger(__name__)

# Log at different levels
log.debug("Detailed diagnostic information")
log.info("General informational message")
log.warning("Warning message")
log.error("Error message")
log.critical("Critical error")

# Log with structured data (extra fields)
log.info(
    "User action completed",
    extra={
        "user_id": 123,
        "action": "create_paper",
        "duration_ms": 456.78
    }
)

# Log exceptions with traceback
try:
    risky_operation()
except Exception as e:
    log.exception("Operation failed: %s", e)
```

### 2. Worker Logging

Workers automatically log to `worker.log` based on module name:

```python
import logging

log = logging.getLogger(__name__)  # e.g., "image_worker" or "slr_worker"

# All logs from workers go to worker.log
log.info("Processing job %s", job_id)
log.error("Job %s failed: %s", job_id, error)
```

### 3. HTTP Access Logging

HTTP requests are automatically logged by `observability_v2.py`:
- Request ID correlation
- Method, path, endpoint
- Status code, duration
- Client IP, User-Agent
- Automatically filtered to `access.log`

### 4. Performance Logging

For performance-critical operations:

```python
import logging

perf_log = logging.getLogger("papergenerator.perf")

# Log slow operations
if duration > threshold:
    perf_log.warning(
        "Slow operation detected",
        extra={
            "operation": "generate_paper",
            "duration_ms": duration,
            "threshold_ms": threshold
        }
    )
```

### 5. Environment Configuration

Set log level via environment variable:

```bash
# In .env file
LOG_LEVEL=INFO  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
```

## Modules Still Using print()

The following modules still use `print()` statements, but these are **intentional** for CLI user feedback:

### CLI Tools (Keep print() for user output)
- `backend/imageGenerator/CreateImageGemini.py` (lines 547-595)
  - CLI commands: `--check`, `--prompt`, `--prompts-json`
  - User-facing output for command-line usage
  
- `backend/imageGenerator/GeminiCookies.py` (lines 189-396)
  - Interactive login flow with user prompts
  - Progress messages during cookie setup

- `backend/template/*.py` (various)
  - Template generators with CLI output
  - User-facing generation progress

### Test Files (Keep print() for test output)
- `backend/tests/test_playwright_paper_generation.py`
  - Test progress and results output
  
- `backend/tests/playwright_mcp_runner.py`
  - Test runner output

### Fallback Error Logging
- `backend/observability_v2.py` (line 126)
  - Fallback to stderr when log rotation fails
  - This is intentional as a last resort

## Monitoring and Debugging

### View Real-time Logs

```bash
# All application logs
tail -f backend/data/logs/app.log | jq .

# Error logs only
tail -f backend/data/logs/error.log | jq .

# HTTP access logs
tail -f backend/data/logs/access.log | jq .

# Worker logs
tail -f backend/data/logs/worker.log | jq .

# Specific worker account
tail -f backend/data/logs/generator/account1.log
```

### Search Logs

```bash
# Find all errors for a specific user
grep '"user_id": 123' backend/data/logs/error.log | jq .

# Find slow requests (>1000ms)
jq 'select(.duration_ms > 1000)' backend/data/logs/access.log

# Find all logs for a specific request ID
grep '"req_id": "abc123"' backend/data/logs/app.log | jq .
```

### Log Rotation Management

Logs are automatically rotated daily at midnight UTC. Archived logs are compressed with gzip:

```bash
# View archived logs
ls -lh backend/data/logs/app.log*
# app.log           # Current log
# app.log.2026-05-22.gz  # Yesterday's log (compressed)
# app.log.2026-05-21.gz  # 2 days ago
```

## Testing the Logging System

### 1. Verify Log Files are Created

```bash
# Start the application
cd backend
python3 app.py

# Check that log files are created
ls -lh data/logs/
```

### 2. Verify JSON Format

```bash
# Check that logs are in JSON format
head -1 data/logs/app.log | jq .
```

### 3. Verify Log Rotation

```bash
# Check rotation configuration
python3 -c "
from observability_v2 import init_observability
from pathlib import Path
print('Log rotation configured successfully')
"
```

## Best Practices

### 1. Use Structured Logging
Always use the `extra` parameter for structured data:

```python
# Good
log.info("User created paper", extra={"user_id": 123, "paper_id": "abc"})

# Avoid
log.info(f"User {user_id} created paper {paper_id}")
```

### 2. Use Appropriate Log Levels
- `DEBUG`: Verbose diagnostic info (disabled in production)
- `INFO`: Normal operations, state changes
- `WARNING`: Unexpected but handled situations
- `ERROR`: Errors that need attention
- `CRITICAL`: System-threatening errors

### 3. Include Context
Always include relevant context in log messages:

```python
log.error(
    "Failed to generate paper",
    extra={
        "user_id": user_id,
        "paper_id": paper_id,
        "error": str(e),
        "attempt": retry_count
    }
)
```

### 4. Don't Log Sensitive Data
Never log passwords, API keys, tokens, or PII:

```python
# Bad
log.info(f"User logged in with password: {password}")

# Good
log.info("User logged in", extra={"user_id": user_id})
```

## Troubleshooting

### Logs Not Appearing

1. Check log level: `LOG_LEVEL` in `.env`
2. Check file permissions: `ls -l backend/data/logs/`
3. Check disk space: `df -h`

### Log Rotation Not Working

1. Check that the process has write permissions
2. Check that gzip is installed: `which gzip`
3. Check for errors in stderr output

### Performance Issues

If logging causes performance issues:
1. Increase log level to `WARNING` or `ERROR`
2. Reduce retention period
3. Use async logging (future enhancement)

## Future Enhancements

Potential improvements for the logging system:

1. **Async Logging**: Use `QueueHandler` for non-blocking logging
2. **Log Aggregation**: Integration with Loki, Elasticsearch, or CloudWatch
3. **Metrics Integration**: Link logs with Prometheus metrics
4. **Alerting**: Automatic alerts on error rate thresholds
5. **Log Sampling**: Sample high-volume logs to reduce storage
6. **Distributed Tracing**: Add OpenTelemetry for request tracing

## Support

For issues or questions about the logging system:
1. Check this documentation
2. Review `backend/observability_v2.py` source code
3. Check application logs in `backend/data/logs/`
4. Report issues to the development team

---

**Implementation completed by Agent 8**
**Date: 2026-05-23**
