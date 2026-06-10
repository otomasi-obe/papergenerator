"""
Shared Hourly Log Handler
==========================
Reusable file handler that creates per-hour directory structure.
Format: {base_dir}/YYYY-MM-DD-HH/{filename}.log

Used by:
- global_logger.py (backend core logs)
- gunicorn.conf.py (gunicorn access/error logs)
- observability_v2.py (app/error/access/worker/perf logs)
- logging_api.py (frontend logs)
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path


class HourlyFileHandler(logging.FileHandler):
    """File handler that creates hourly subdirectories and rotates automatically.
    
    Directory structure:
        {base_dir}/YYYY-MM-DD-HH/{filename}
    
    Args:
        base_dir: Base directory for all hourly log folders
        filename: Name of the log file (e.g., "backend.log")
        level: Minimum log level
    """

    def __init__(self, base_dir, filename, level=logging.INFO):
        self.base_dir = Path(base_dir)
        self.filename = filename
        self._current_hour = None
        self.base_dir.mkdir(parents=True, exist_ok=True)
        super().__init__(self._get_current_path(), mode='a', encoding='utf-8')
        self.setLevel(level)
        self.setFormatter(HourlyJSONFormatter())

    def _get_current_hour_dir(self):
        now = datetime.now(timezone.utc)
        return self.base_dir / now.strftime("%Y-%m-%d-%H")

    def _get_current_path(self):
        hour_dir = self._get_current_hour_dir()
        hour_dir.mkdir(parents=True, exist_ok=True)
        return str(hour_dir / self.filename)

    def emit(self, record):
        now_hour = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
        if now_hour != self._current_hour:
            try:
                if self.stream and not self.stream.closed:
                    self.stream.close()
                self.baseFilename = self._get_current_path()
                self.stream = self._open()
                self._current_hour = now_hour
            except Exception:
                pass
        super().emit(record)


class HourlyJSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    _RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message",
    }

    def format(self, record):
        payload = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k not in self._RESERVED and not k.startswith("_"):
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)
