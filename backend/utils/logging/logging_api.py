"""
Frontend Logging Endpoint
==========================
Receives structured logs from frontend and writes them to per-hour files
under backend/log/frontend/YYYY-MM-DD-HH/frontend.log
"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from utils.core.hourly_log_handler import HourlyFileHandler

# All application logs belong under backend/log.
BACKEND_DIR = Path(__file__).resolve().parents[2]
FRONTEND_LOG_BASE = BACKEND_DIR / "log" / "frontend"

log = logging.getLogger("papergenerator.frontend")

logging_api = Blueprint("logging_api", __name__)

# Dedicated logger for frontend logs written to file
_frontend_file_logger = logging.getLogger("papergenerator.frontend.file")
_frontend_handler = None


def _get_frontend_handler():
    """Lazy-init the frontend hourly file handler."""
    global _frontend_handler
    if _frontend_handler is None:
        FRONTEND_LOG_BASE.mkdir(parents=True, exist_ok=True)
        _frontend_handler = HourlyFileHandler(
            str(FRONTEND_LOG_BASE), "frontend.log", level=logging.DEBUG
        )
        _frontend_file_logger.addHandler(_frontend_handler)
        _frontend_file_logger.setLevel(logging.DEBUG)
        _frontend_file_logger.propagate = False
    return _frontend_handler


def _write_frontend_log(entry):
    """Write a single frontend log entry to the hourly log file."""
    try:
        _get_frontend_handler()

        payload = {
            "ts": entry.get("ts", datetime.now(timezone.utc).isoformat()),
            "level": entry.get("level", "INFO"),
            "logger": "frontend",
            "msg": entry.get("msg", ""),
            "source": "frontend",
        }

        for key in ["req_id", "url", "method", "status", "duration_ms",
                     "action", "operation", "error", "filename", "lineno",
                     "colno", "_user_id"]:
            if key in entry and entry[key] is not None:
                payload[key] = entry[key]

        # Use the logger to write (goes through HourlyFileHandler → per-hour dir)
        level_name = entry.get("level", "INFO").upper()
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARN": logging.WARNING,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        py_level = level_map.get(level_name, logging.INFO)

        record = _frontend_file_logger.makeRecord(
            "frontend", py_level, "", 0, payload["msg"], (), None
        )
        for k, v in payload.items():
            setattr(record, k, v)
        _frontend_file_logger.handle(record)

    except Exception:
        log.exception("Failed to write frontend log entry")


def cleanup_old_frontend_logs(max_age_days=7):
    """Hapus folder frontend log yang lebih tua dari max_age_days."""
    try:
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_days * 86400)
        for entry in FRONTEND_LOG_BASE.iterdir():
            if entry.is_dir() and entry.name.startswith("20"):
                try:
                    dir_time = datetime.strptime(entry.name, "%Y-%m-%d-%H").timestamp()
                    if dir_time < cutoff:
                        shutil.rmtree(entry)
                except (ValueError, OSError):
                    pass
    except Exception:
        pass


@logging_api.route("/api/logs/frontend", methods=["POST"])
@jwt_required(optional=True)
def receive_frontend_logs():
    """
    Receive logs from frontend and write them to per-hour files.

    Expected payload:
    {
        "logs": [
            {
                "ts": "2026-05-23T08:15:00.000Z",
                "level": "ERROR",
                "msg": "API call failed",
                "req_id": "1234-abcd",
                "url": "/papers",
                "method": "POST",
                "status": 500,
                ...
            }
        ]
    }
    """
    try:
        user_id = get_jwt_identity() if get_jwt_identity() else "anonymous"
        data = request.get_json(silent=True)

        if not data or "logs" not in data:
            return jsonify({"error": "Invalid payload"}), 400

        logs = data.get("logs", [])
        if not isinstance(logs, list):
            return jsonify({"error": "logs must be an array"}), 400

        for entry in logs[:200]:
            if not isinstance(entry, dict):
                continue

            entry["_user_id"] = user_id
            _write_frontend_log(entry)

        return jsonify({"status": "ok", "received": len(logs)}), 200

    except Exception:
        log.exception("Failed to process frontend logs")
        return jsonify({"error": "Internal server error"}), 500
