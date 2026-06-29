"""
Global Hourly Logger
=====================
Semua aktivitas backend tercatat di sini.
Log dibagi per jam: backend/log/YYYY-MM-DD-HH/

File:
- backend.log: Semua aktivitas (INFO+)
- error.log: Error saja (ERROR+)
- access.log: HTTP request/response

TIDAK BOLEH ada logging di tempat lain selain di sini.
"""

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from utils.core.hourly_log_handler import HourlyFileHandler

# Base log directory
BACKEND_DIR = Path(__file__).parent.parent.parent  # backend/
LOG_BASE = BACKEND_DIR / "log"


def init_global_logging():
    """Inisialisasi sistem logging global. Panggil sekali di startup."""
    LOG_BASE.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    # backend.log - semua aktivitas
    backend_handler = HourlyFileHandler(LOG_BASE, "backend.log", level=logging.INFO)

    # error.log - error saja
    error_handler = HourlyFileHandler(LOG_BASE, "error.log", level=logging.ERROR)

    # access.log - HTTP request (filter khusus)
    access_handler = HourlyFileHandler(LOG_BASE, "access.log", level=logging.INFO)
    access_handler.addFilter(lambda r: getattr(r, '_is_access', False))

    # stdout untuk Docker/systemd
    from utils.core.hourly_log_handler import HourlyJSONFormatter
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(HourlyJSONFormatter())
    stream_handler.setLevel(logging.INFO)

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    root.setLevel(log_level)
    root.addHandler(backend_handler)
    root.addHandler(error_handler)
    root.addHandler(access_handler)
    root.addHandler(stream_handler)

    return logging.getLogger("papergenerator.global")


def get_logger(name):
    """Dapatkan logger untuk modul."""
    return logging.getLogger(name)


def log_access(method, path, status, duration_ms, user_id=None, ip=None, extra=None):
    """Catat HTTP request ke access.log."""
    logger = logging.getLogger("papergenerator.access")
    record = logger.makeRecord(
        "papergenerator.access", logging.INFO, "", 0,
        f"{method} {path} {status}", (), None
    )
    record._is_access = True
    record.method = method
    record.path = path
    record.status = status
    record.duration_ms = duration_ms
    if user_id:
        record.user_id = user_id
    if ip:
        record.ip = ip
    if extra:
        for k, v in extra.items():
            setattr(record, k, v)
    logger.handle(record)


def cleanup_old_logs(max_age_days=7):
    """Hapus folder log yang lebih tua dari max_age_days."""
    try:
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_days * 86400)
        for entry in LOG_BASE.iterdir():
            if entry.is_dir() and entry.name.startswith("20"):
                try:
                    dir_time = datetime.strptime(entry.name, "%Y-%m-%d-%H").timestamp()
                    if dir_time < cutoff:
                        shutil.rmtree(entry)
                except (ValueError, OSError):
                    pass
    except Exception:
        pass
