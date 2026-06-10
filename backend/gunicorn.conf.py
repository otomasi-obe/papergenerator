"""
Gunicorn production configuration
Server: 2 CPU cores, 7.6GB RAM
Target: 500 concurrent users
Strategy: sync workers with threading (compatible with Flask + SQLAlchemy)
  gevent has pre-fork incompatibilities with SQLAlchemy connection pool
  - 4 workers × 4 threads = 16 real concurrent requests
  - nginx keepalive + gunicorn backlog handles burst to 500
"""

import os

# ── Workers ──────────────────────────────────────────────────────────────────
# gthread: sync worker with threads (safe with SQLAlchemy connection pooling)
worker_class = "gthread"
workers = 4  # Reduced to 4 workers to save memory
threads = 8  # 8 threads per worker = 32 total concurrent requests
# Each thread handles one request; OS schedules I/O

# ── Timeouts ─────────────────────────────────────────────────────────────────
timeout = 1800  # AI generation max worst-case: 1 model × 3 retry × 600s = 1800s
graceful_timeout = 120  # give in-flight requests 120s to finish during reload
keepalive = 10  # keep connection alive 10s between requests (nginx upstream)

# ── Binding ──────────────────────────────────────────────────────────────────
bind = f"127.0.0.1:{os.getenv('BACKEND_PORT', '8001')}"
backlog = 2048  # OS-level queue for unaccepted connections

# ── Security ─────────────────────────────────────────────────────────────────
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# ── Process naming ───────────────────────────────────────────────────────────
proc_name = "paper-generator-api"
default_proc_name = "paper-generator-api"

# ── Logging ──────────────────────────────────────────────────────────────────
# Per-hour logging via logconfig_dict with HourlyFileHandler.
# Gunicorn's built-in accesslog/errorlog are disabled; all logging goes through
# Python's logging.config.dictConfig to backend/log/YYYY-MM-DD-HH/
from pathlib import Path

_log_dir_env = os.getenv("GUNICORN_LOG_DIR")
_default_log_dir = Path(__file__).resolve().parent / "log"
_log_dir = Path(_log_dir_env) if _log_dir_env else _default_log_dir
_log_dir.mkdir(parents=True, exist_ok=True)

# Disable gunicorn's built-in flat-file logging
accesslog = None
errorlog = None
loglevel = "info"

logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "utils.core.hourly_log_handler.HourlyJSONFormatter",
        }
    },
    "handlers": {
        "gunicorn_access": {
            "()": "utils.core.hourly_log_handler.HourlyFileHandler",
            "base_dir": str(_log_dir),
            "filename": "gunicorn-access.log",
            "level": "INFO",
        },
        "gunicorn_error": {
            "()": "utils.core.hourly_log_handler.HourlyFileHandler",
            "base_dir": str(_log_dir),
            "filename": "gunicorn-error.log",
            "level": "INFO",
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "level": "INFO",
        },
    },
    "loggers": {
        "gunicorn.access": {
            "handlers": ["gunicorn_access"],
            "level": "INFO",
            "propagate": False,
        },
        "gunicorn.error": {
            "handlers": ["gunicorn_error", "console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

# ── Performance ──────────────────────────────────────────────────────────────
# NOTE: preload_app disabled — causes issues with gevent/thread workers + SQLAlchemy
preload_app = False
max_requests = 5000  # recycle worker after 5000 requests (prevent memory leaks)
max_requests_jitter = 500  # stagger recycling so not all workers restart at once

# ── Worker tmp heartbeat dir ─────────────────────────────────────────────────
worker_tmp_dir = "/dev/shm"  # use RAM for heartbeat files (faster than disk)


# ── Shutdown noise suppression ───────────────────────────────────────────────
# gthread + Python 3.10 logs harmless 'Exception ignored in: <module threading>'
# on SIGINT (atexit / _threads_queues weakref race). Suppress at the worker
# level so backend-err.log stays signal-only.
def post_fork(server, worker):
    import atexit
    import contextlib
    import sys

    _orig_excepthook = sys.excepthook

    def _silent_threading_excepthook(exc_type, exc, tb):
        if isinstance(exc, SystemExit) and (exc.code == 0 or exc.code is None):
            return
        _orig_excepthook(exc_type, exc, tb)

    sys.excepthook = _silent_threading_excepthook

    @atexit.register
    def _silence_stderr_on_shutdown():
        with contextlib.suppress(Exception):
            sys.stderr.flush()
