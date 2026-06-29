"""
Server-side math CAPTCHA module.

Generates simple arithmetic challenges (e.g. "What is 3 + 7?"), stores the
answer in Redis with a 5-minute TTL, and exposes verify/require helpers.

Controlled by CAPTCHA_ENABLED env var (default: true in production, false in dev).
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import uuid
from typing import Optional

from flask import request

log = logging.getLogger(__name__)

CAPTCHA_TTL = 300  # 5 minutes
MAX_FAILED_ATTEMPTS = 3  # After N failed logins from same IP, require CAPTCHA


def captcha_enabled() -> bool:
    """Check if CAPTCHA protection is enabled via env var."""
    val = os.getenv("CAPTCHA_ENABLED", "").lower().strip()
    if val in ("true", "1", "yes"):
        return True
    if val in ("false", "0", "no"):
        return False
    # Default: enabled in production, disabled in dev/testing
    return os.getenv("FLASK_ENV") == "production"


def _get_redis():
    """Get Redis client, returns None if unavailable."""
    from utils.core.redis_client import get_redis
    return get_redis()


def _generate_challenge() -> tuple[str, int]:
    """Generate a simple arithmetic CAPTCHA. Returns (question, answer)."""
    ops = [
        ("+", lambda a, b: a + b),
        ("−", lambda a, b: a - b),
        ("×", lambda a, b: a * b),
    ]
    op_symbol, op_fn = random.choice(ops)

    if op_symbol == "×":
        a = random.randint(2, 12)
        b = random.randint(2, 9)
    elif op_symbol == "−":
        a = random.randint(5, 30)
        b = random.randint(1, a)  # ensure non-negative result
    else:
        a = random.randint(1, 30)
        b = random.randint(1, 30)

    answer = op_fn(a, b)
    question = f"What is {a} {op_symbol} {b}?"
    return question, answer


def generate_captcha() -> dict:
    """
    Generate a new CAPTCHA challenge.
    Returns {"captcha_id": ..., "question": ...} or None if CAPTCHA disabled/unavailable.
    """
    captcha_id = str(uuid.uuid4())
    question, answer = _generate_challenge()

    rc = _get_redis()
    if rc is not None:
        try:
            rc.set(f"captcha:{captcha_id}", str(answer), ex=CAPTCHA_TTL)
        except Exception as e:
            log.warning("captcha: failed to store in Redis: %s", e)
            # Fallback: store in-memory (per-process, less reliable but functional)
            _fallback_store[captcha_id] = (str(answer), os.times().elapsed + CAPTCHA_TTL)
    else:
        _fallback_store[captcha_id] = (str(answer), os.times().elapsed + CAPTCHA_TTL)

    return {"captcha_id": captcha_id, "question": question}


# In-memory fallback when Redis is unavailable (per-process)
_fallback_store: dict[str, tuple[str, float]] = {}


def verify_captcha(captcha_id: str, answer: str) -> bool:
    """
    Verify a CAPTCHA answer. Consumes the captcha on success or failure.
    Returns True if answer is correct.
    """
    if not captcha_id or not answer:
        return False

    answer = str(answer).strip()
    rc = _get_redis()
    stored_answer: Optional[str] = None

    if rc is not None:
        try:
            stored_answer = rc.get(f"captcha:{captcha_id}")
            # Consume the captcha regardless of result (one-time use)
            rc.delete(f"captcha:{captcha_id}")
        except Exception as e:
            log.warning("captcha: Redis error during verify: %s", e)
    else:
        # Fallback
        entry = _fallback_store.pop(captcha_id, None)
        if entry:
            stored_answer, expiry = entry
            if os.times().elapsed > expiry:
                stored_answer = None  # expired

    if stored_answer is None:
        return False

    return stored_answer == answer


def _get_client_ip() -> str:
    """Get the client IP, respecting X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _failed_attempts_key() -> str:
    """Redis key for tracking failed login attempts per IP."""
    return f"captcha:failed_login:{_get_client_ip()}"


def get_failed_login_attempts() -> int:
    """Get the number of failed login attempts from the current IP."""
    rc = _get_redis()
    if rc is not None:
        try:
            val = rc.get(_failed_attempts_key())
            return int(val) if val else 0
        except Exception:
            pass
    return 0


def increment_failed_attempts() -> None:
    """Increment failed login attempt counter for the current IP (15-min TTL)."""
    rc = _get_redis()
    if rc is not None:
        try:
            key = _failed_attempts_key()
            rc.incr(key)
            rc.expire(key, 900)  # 15 minute window
        except Exception as e:
            log.warning("captcha: failed to increment attempts: %s", e)


def reset_failed_attempts() -> None:
    """Clear failed login counter after successful login."""
    rc = _get_redis()
    if rc is not None:
        try:
            rc.delete(_failed_attempts_key())
        except Exception:
            pass


def captcha_required_for_login() -> bool:
    """Check if CAPTCHA is required for login (after N failed attempts from same IP)."""
    if not captcha_enabled():
        return False
    return get_failed_login_attempts() >= MAX_FAILED_ATTEMPTS
