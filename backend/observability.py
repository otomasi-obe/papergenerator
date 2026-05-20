"""
Observability primitives: structured JSON logging, request-id correlation,
Prometheus metrics, and a deeper /api/healthz check.
Wire into the Flask app via init_observability(app).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
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


def _configure_logging(log_file: Path) -> None:
    fmt = JSONFormatter()

    # Reset any existing handlers from the previous logging.basicConfig call.
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    file_h = logging.FileHandler(log_file, encoding="utf-8")
    file_h.setFormatter(fmt)
    stream_h = logging.StreamHandler(sys.stdout)
    stream_h.setFormatter(fmt)
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    root.addHandler(file_h)
    root.addHandler(stream_h)


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
    _configure_logging(log_file)
    log = logging.getLogger("papergenerator.obs")

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
