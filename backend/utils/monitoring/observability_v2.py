"""
Enhanced Observability Module with Log Rotation
================================================
Structured JSON logging with daily rotation, compression, and retention policies.

Log Files:
- app.log: All application logs (INFO+), 7-day retention
- error.log: Error logs only (ERROR+), 30-day retention
- access.log: HTTP access logs (INFO+), 7-day retention
- worker.log: Background worker logs (INFO+), 7-day retention
- perf.log: Performance logs (WARNING+), 7-day retention

Features:
- TimedRotatingFileHandler with daily rotation at midnight UTC
- Gzip compression for archived logs
- JSON format for structured logging
- Separate handlers for different log categories
- Automatic log cleanup based on retention policies
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

from flask import Flask, Response, g, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import text
from werkzeug.exceptions import HTTPException

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
    ["status"],  # done | error | timeout
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
RATE_LIMIT_REQUESTS = Counter(
    "rate_limit_requests_total",
    "Total requests processed by rate limiter.",
    ["endpoint", "status"],
)
RATE_LIMIT_BREACHES = Counter(
    "rate_limit_breaches_total",
    "Rate limit violations by endpoint and limit type.",
    ["endpoint", "limit_type"],
)
RATE_LIMIT_CURRENT_USAGE = Gauge(
    "rate_limit_current_usage",
    "Current rate limit usage percentage by endpoint.",
    ["endpoint", "identifier"],
)


# ── Structured JSON logging ─────────────────────────────────────────────────
class JSONFormatter(logging.Formatter):
    """Render every log record as a single-line JSON object so log aggregators
    (Loki, Grafana, ELK) can parse fields without regex.
    """

    _RESERVED = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
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
        with open(source, "rb") as f_in:
            with gzip.open(dest, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
        Path(source).unlink()
    except Exception as e:
        # Don't crash the app if compression fails - log to stderr and root logger
        logging.error("log_rotation_failed", extra={"source": source, "error": str(e)})
        print(f"WARNING: Log rotation failed for {source}: {e}", file=sys.stderr)


from utils.core.hourly_log_handler import HourlyFileHandler


def _create_rotating_handler(
    log_dir: Path,
    filename: str,
    level: int = logging.INFO,
) -> HourlyFileHandler:
    """Create a per-hour rotating file handler.

    Args:
        log_dir: Base directory for hourly log folders
        filename: Log file name (e.g., 'app.log')
        level: Minimum log level

    Returns:
        Configured HourlyFileHandler
    """
    return HourlyFileHandler(str(log_dir), filename, level=level)


def _configure_logging(log_dir: Path) -> None:
    """Configure root logger with per-hour rotating file handlers and stdout.

    Creates log files in per-hour directories:
    - backend.log: All logs (INFO+)
    - error.log: Errors only (ERROR+)
    - access.log: HTTP access logs (INFO+)
    - worker.log: Background worker logs (INFO+)
    - perf.log: Performance logs (WARNING+)
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    # Reset any existing handlers
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    # Main application log (all levels)
    app_handler = _create_rotating_handler(log_dir, "backend.log", level=logging.INFO)

    # Error log (errors only)
    error_handler = _create_rotating_handler(log_dir, "error.log", level=logging.ERROR)

    # Access log (HTTP requests)
    access_handler = _create_rotating_handler(log_dir, "access.log", level=logging.INFO)
    access_handler.addFilter(lambda r: getattr(r, '_is_access', False))

    # Worker log (background workers)
    worker_handler = _create_rotating_handler(log_dir, "worker.log", level=logging.INFO)
    worker_handler.addFilter(
        lambda r: any(x in r.name for x in ["worker", "slr", "image", "gemini"])
    )

    # Performance log (warnings about slow operations)
    perf_handler = _create_rotating_handler(log_dir, "perf.log", level=logging.WARNING)
    perf_handler.addFilter(lambda r: "perf" in r.name.lower())

    # Stdout for Docker/systemd log collection
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(JSONFormatter())
    stream_handler.setLevel(logging.INFO)

    # Configure root logger
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    root.setLevel(log_level)
    root.addHandler(app_handler)
    root.addHandler(error_handler)
    root.addHandler(access_handler)
    root.addHandler(worker_handler)
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
    # Use backend/log/ as the canonical log directory
    log_dir = Path(__file__).parent.parent.parent / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    _configure_logging(log_dir)

    log = logging.getLogger("papergenerator.obs")
    log.info(
        "Observability initialized",
        extra={
            "log_dir": str(log_dir),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
        },
    )

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

        # Don't log HTTP exceptions as errors (they're expected client errors)
        if isinstance(e, HTTPException):
            # Log as info/warning, not exception
            log.info(
                "http_exception",
                extra={
                    "req_id": rid,
                    "path": request.path,
                    "status": e.code,
                    "exception_name": e.name,
                },
            )
            return e  # Return HTTP exception as-is

        # Only log unexpected exceptions
        log.exception("unhandled_error", extra={"req_id": rid, "path": request.path})
        raise e  # Re-raise non-HTTP exceptions

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
