import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import g
from utils.core.hourly_log_handler import HourlyFileHandler

CHAT_LOG_BASE = Path(__file__).parent.parent.parent / "log" / "chat"

_chat_file_logger = logging.getLogger("papergenerator.chat.file")
_chat_handler = None


def _get_chat_handler():
    global _chat_handler
    if _chat_handler is None:
        CHAT_LOG_BASE.mkdir(parents=True, exist_ok=True)
        _chat_handler = HourlyFileHandler(
            str(CHAT_LOG_BASE), "chat_calls.jsonl", level=logging.DEBUG
        )
        _chat_file_logger.addHandler(_chat_handler)
        _chat_file_logger.setLevel(logging.DEBUG)
        _chat_file_logger.propagate = False
    return _chat_handler


def _resolve_correlation_id():
    try:
        return g.correlation_id
    except Exception:
        return uuid.uuid4().hex[:12]


def log_chat_call(paper_id, conv_id, role, payload, correlation_id=None):
    try:
        _get_chat_handler()
        entry = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "correlation_id": correlation_id or _resolve_correlation_id(),
            "paper_id": str(paper_id or "_global"),
            "conv_id": conv_id,
            "role": role,
            "payload": payload,
        }
        line = json.dumps(entry, default=str, ensure_ascii=False)
        record = _chat_file_logger.makeRecord(
            "chat", logging.INFO, "", 0, line, (), None
        )
        _chat_file_logger.handle(record)
    except Exception as e:
        logging.getLogger(__name__).warning("log_chat_call failed: %s", e)
