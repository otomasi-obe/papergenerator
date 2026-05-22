"""
Enhanced Observability Module with Log Rotation
================================================
Structured JSON logging with daily rotation, compression, and retention policies.

Changes from original:
- Added TimedRotatingFileHandler with daily rotation
- Added gzip compression for archived logs
- Separate handlers for errors and performance logs
- 7-day retention for app logs, 30-day for errors
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
import sys
import time
import uuid
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from flask import Flask, Response, g, request, jsonify
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import text


# ── Metrics (process-wide, registered once at import) ───────────────────────
REQ_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests served by the API.",
    ["method", "endpoint", "status"],
)
REQ_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Request latency in seconds.",
    ["method", "endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)
REQ_IN_FLIGHT = Gauge(
    "http_requests_in_flight",
    "Requests currently being processed.",
)
AI_GENERATION_COUNT = Counter(
    "ai_generation_total",
    "AI paper-generation jobs by terminal status.",
    ["status"],   # done | error | timeout
)
LOG_ERRORS_TOTAL = Counter(
    "log_errors_total",
    "Total errors logged by category.",
    ["error_type", "error_code"],
)
SLOW_OPERATIONS_TOTAL = Counter(
    "slow_operations_total",
    "Operations exceeding performance threshold.",
    ["operation", "threshold_ms"],
)
FRONTEND_ERRORS_TOTAL = Counter(
    "frontend_errors_total",
    "Frontend errors reported to backend.",
    ["error_type", "page"],
)


# ── Structured JSON logging ─────────────────────────────────────────────────
class JSONFormatter(logging.Formatter):
    """Render every log record as a single-line JSON object so log aggregators
    (Loki, Grafana, ELK) can parse fields without regex.
    """

    _RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Surface any structured extras the caller passed via logger.info(..., extra={...}).
        for k, v in record.__dict__.items():
            if k not in self._RESERVED and not k.startswith("_"):
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


# ── Log rotation helpers ────────────────────────────────────────────────────
def _namer(default_name: str) -> str:
    """Add .gz extension to rotated logs."""
    return default_name + ".gz"


def _rotator(source: str, dest: str) -> None:
    """Compress rotated logs with gzip."""
    try:
        with open(source, 'rb') as f_in:
            with gzip.open(dest, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        Path(source).unlink()
    except Exception as e:
        # Don't crash the app if compression fails - log to stderr
        print(f"WARNING: Log rotation failed for {source}: {e}", file=sys.stderr)


def _create_rotating_handler(
    log_dir: Path,
    filename: str,
    level: int = logging.INFO,
    when: str = 'midnight',
    backup_count: int = 7,
) -> TimedRotatingFileHandler:
    """Create a rotating file handler with compression.
    
    Args:
        log_dir: Directory to store logs
        filename: Log file name (e.g., 'app.log')
        level: Minimum log level
        when: Rotation interval ('midnight', 'H', 'D', etc.)
        backup_count: Number of backup files to keep
    
    Returns:
        Configured TimedRotatingFileHandler
    """
    handler = TimedRotatingFileHandler(
        log_dir / filename,
        when=when,
        interval=1,
        backupCount=backup_count,
        encoding='utf-8',
        utc=True,
    )
    handler.namer = _namer
    handler.rotator = _rotator
    handler.setLevel(level)
    handler.setFormatter(JSONFormatter())
    return handler


def _configure_logging(log_dir: Path) -> None:
    """Configure root logger with rotating file handlers and stdout.
    
    Creates three log files:
    - app.log: All logs (INFO+), 7-day retention
    - errors.log: Errors only (ERROR+), 30-day retention
    - perf.log: Performance logs (WARNING+), 7-day retention
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Reset any existing handlers
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    
    # Main application log (all levels, 7-day retention)
    app_handler = _create_rotating_handler(
        log_dir, 'app.log', level=logging.INFO, backup_count=7
    )
    
    # Error log (errors only, 30-day retention for compliance)
    error_handler = _create_rotating_handler(
        log_dir, 'errors.log', level=logging.ERROR, backup_count=30
    )
    
    # Performance log (warnings about slow operations, 7-day retention)
    perf_handler = _create_rotating_handler(
        log_dir, 'perf.log', level=logging.WARNING, backup_count=7
    )
    # Only capture performance-related logs
    perf_handler.addFilter(lambda r: 'perf' in r.name.lower())
    
    # Stdout for Docker/systemd log collection
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(JSONFormatter())
    stream_handler.setLevel(logging.INFO)
    
    # Configure root logger
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    root.setLevel(log_level)
    root.addHandler(app_handler)
    root.addHandler(error_handler)
    root.addHandler(perf_handler)
    root.addHandler(stream_handler)


# ── Health checks ───────────────────────────────────────────────────────────
def _check_db(db) -> tuple[bool, str | None]:
    try:
        db.session.execute(text("SELECT 1"))
        return True, None
    except Exception as e:
        return False, str(e)[:200]


def _check_disk(path: Path, min_free_mb: int = 200) -> tuple[bool, dict]:
    try:
        st = os.statvfs(path)
        free_mb = (st.f_bavail * st.f_frsize) // (1024 * 1024)
        return free_mb >= min_free_mb, {"free_mb": free_mb, "min_required_mb": min_free_mb}
    except Exception as e:
        return False, {"error": str(e)[:200]}


# ── Wiring ──────────────────────────────────────────────────────────────────
def init_observability(app: Flask, db, *, log_file: Path) -> None:
    """Initialize observability: logging, metrics, health checks.
    
    Args:
        app: Flask application instance
        db: SQLAlchemy database instance
        log_file: Path to main log file (parent dir will contain all logs)
    """
    # Use parent directory for all logs
    log_dir = log_file.parent / "logs"
    _configure_logging(log_dir)
    
    log = logging.getLogger("papergenerator.obs")
    log.info("Observability initialized", extra={
        "log_dir": str(log_dir),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
    })

    @app.before_request
    def _start_timer():
        g._req_started_at = time.perf_counter()
        g._req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        REQ_IN_FLIGHT.inc()

    @app.after_request
    def _record(resp):
        # endpoint can be None for 404s — bucket those into a single label.
        endpoint = request.endpoint or "_unmatched"
        method = request.method
        status = str(resp.status_code)
        elapsed = time.perf_counter() - getattr(g, "_req_started_at", time.perf_counter())

        REQ_COUNT.labels(method, endpoint, status).inc()
        REQ_LATENCY.labels(method, endpoint).observe(elapsed)
        REQ_IN_FLIGHT.dec()

        rid = getattr(g, "_req_id", "")
        resp.headers["X-Request-ID"] = rid

        # Skip health/metrics from access log noise — they hit every few seconds.
        if endpoint not in ("metrics", "healthz", "health"):
            log.info(
                "http",
                extra={
                    "req_id": rid,
                    "method": method,
                    "path": request.path,
                    "endpoint": endpoint,
                    "status": resp.status_code,
                    "duration_ms": round(elapsed * 1000, 2),
                    "ip": request.headers.get("X-Forwarded-For", request.remote_addr or ""),
                    "ua": request.headers.get("User-Agent", "")[:120],
                },
            )
        return resp

    @app.errorhandler(Exception)
    def _on_unhandled(e):
        rid = getattr(g, "_req_id", "")
        log.exception("unhandled_error", extra={"req_id": rid, "path": request.path})
        # Re-raise so Flask's default handler still produces the 500 response.
        raise e

    @app.route("/metrics", methods=["GET"])
    @app.route("/api/metrics", methods=["GET"])
    def metrics():
        # Prometheus exposition format — keep open to localhost / scraper only via firewall/nginx.
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    @app.route("/api/healthz", methods=["GET"])
    def healthz():
        """Deeper health check — DB connectivity + disk space.
        /api/health stays as the cheap liveness probe; /api/healthz is readiness.
        """
        db_ok, db_err = _check_db(db)
        disk_ok, disk_meta = _check_disk(Path(app.root_path), min_free_mb=200)

        ok = db_ok and disk_ok
        body = {
            "status": "ok" if ok else "degraded",
            "checks": {
                "db": {"ok": db_ok, **({"error": db_err} if db_err else {})},
                "disk": {"ok": disk_ok, **disk_meta},
            },
        }
        return jsonify(body), 200 if ok else 503
