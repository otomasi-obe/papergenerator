"""
Alibaba Model Studio — Image Generation via TopRouter.

Architecture:
  - Calls TopRouter /v1/images/generations (OpenAI-compatible)
  - Model priority: wan2.7-image-pro > wan2.7-image > qwen-image-2.0-pro > ...
  - Per-model health tracking + exponential backoff
  - Auto-fallback to next model on quota exhaustion / API error
  - Designed as a drop-in provider for image_api.py generate_image()

Env:
  ALIBABA_IMAGE_TOPROUTER_URL  — TopRouter endpoint (default: https://ai.otomasi.app)
  ALIBABA_IMAGE_TOPROUTER_KEY  — TopRouter API key

Usage:
  from tools.image_generation.image_alibaba import generate_image
  image_bytes = generate_image(prompt, out_path, timeout_s=120)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────
TOPROUTER_URL = os.environ.get(
    "ALIBABA_IMAGE_TOPROUTER_URL", "https://ai.otomasi.app"
).rstrip("/")
TOPROUTER_API_KEY = os.environ.get("ALIBABA_IMAGE_TOPROUTER_KEY", "")

    # "wan2.7-image-pro",        # Best quality, 4K
    # "wan2.7-image",            # Fast, 2K
# Best quality → fallback model order
MODEL_PRIORITY = [
    "qwen-image-2.0-pro",      # Qwen best
    "z-image-turbo",           # Fast turbo
    "qwen-image-2.0",          # Qwen standard
    "qwen-image-max",          # Qwen max
    "qwen-image-plus",         # Qwen plus
    "qwen-image",              # Qwen base
    "wan2.6-t2i",              # Wan2.6
    "wan2.5-t2i-preview",      # Wan2.5
    "wan2.2-t2i-plus",
    "wan2.2-t2i-flash",
    "wan2.1-t2i-plus",
    "wan2.1-t2i-turbo",
    "qwen-image-2.0-pro-2026-03-03",
    "qwen-image-2.0-pro-2026-04-22",
    "qwen-image-2.0-2026-03-03",
    "qwen-image-max-2025-12-30",
    "qwen-image-plus-2026-01-09",
]

# Default size — maps to model's native default (auto = omit)
DEFAULT_SIZE = "1024x1024"

# ─── Per-Model Health Tracking ──────────────────────────────────────────
_model_health: dict[str, dict] = {}
_health_lock = threading.Lock()


def _get_health(model: str) -> dict:
    with _health_lock:
        if model not in _model_health:
            _model_health[model] = {
                "success": 0,
                "fail": 0,
                "consecutive_fails": 0,
                "last_success": 0.0,
                "last_fail": 0.0,
                "backoff_until": 0.0,
            }
        return _model_health[model]


def _is_available(model: str) -> bool:
    return time.time() >= _get_health(model)["backoff_until"]


def _record_success(model: str) -> None:
    h = _get_health(model)
    h["success"] += 1
    h["last_success"] = time.time()
    h["consecutive_fails"] = 0
    h["backoff_until"] = 0.0


def _record_failure(model: str, backoff_s: float = 60.0) -> None:
    h = _get_health(model)
    h["fail"] += 1
    h["last_fail"] = time.time()
    h["consecutive_fails"] += 1
    delay = min(backoff_s * (2 ** (h["consecutive_fails"] - 1)), 3600)
    h["backoff_until"] = time.time() + delay
    log.info(
        "Alibaba model %s: fail #%d, backoff %ds (consecutive: %d)",
        model, h["fail"], int(delay), h["consecutive_fails"],
    )


# ─── Public API ──────────────────────────────────────────────────────────

def generate_image(
    prompt: str,
    out_path: str | Path,
    *,
    width: int = 1024,
    height: int = 1024,
    timeout_s: int = 120,
) -> bytes:
    """Generate image via Alibaba Model Studio through TopRouter.

    Tries models in priority order. On quota exhaustion, falls to next model.
    All models exhausted → raises RuntimeError.

    Args:
        prompt: Image description.
        out_path: Where to save the image.
        width: Image width (pixels).
        height: Image height (pixels).
        timeout_s: Total timeout for the API call.

    Returns:
        Raw image bytes.

    Raises:
        RuntimeError: All models failed.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not TOPROUTER_API_KEY:
        raise RuntimeError("ALIBABA_IMAGE_TOPROUTER_KEY not set in environment")

    size = f"{width}x{height}"
    last_error: Optional[Exception] = None
    fallback_count = 0

    for model in MODEL_PRIORITY:
        if not _is_available(model):
            h = _get_health(model)
            remaining = int(h["backoff_until"] - time.time())
            if remaining < 120:  # Only log if backoff is reasonable
                log.debug("Alibaba %s: in backoff (%ds remaining)", model, remaining)
            continue

        try:
            log.info("Alibaba: trying model=%s prompt=%d chars", model, len(prompt))

            resp = requests.post(
                f"{TOPROUTER_URL}/v1/images/generations",
                json={
                    "model": f"alicode-intl/{model}",
                    "prompt": prompt,
                    "n": 1,
                    "size": size,
                },
                headers={
                    "Authorization": f"Bearer {TOPROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=timeout_s,
            )

            if resp.status_code == 200:
                data = resp.json()
                images = data.get("data", [])
                if images:
                    image_url = images[0].get("url")
                    if image_url:
                        # Download actual image
                        img_resp = requests.get(image_url, timeout=30)
                        img_resp.raise_for_status()
                        image_bytes = img_resp.content

                        if len(image_bytes) < 500:
                            raise RuntimeError(
                                f"Downloaded image too small: {len(image_bytes)} bytes"
                            )

                        out_path.write_bytes(image_bytes)
                        _record_success(model)
                        elapsed = resp.elapsed.total_seconds()
                        log.info(
                            "Alibaba %s: SUCCESS %dx%d %dKB in %.1fs",
                            model, width, height, len(image_bytes) // 1024, elapsed,
                        )
                        return image_bytes

                raise RuntimeError("No image URL in response data")

            # ─── Error handling ───────────────────────────────────────
            error_body = {}
            try:
                if resp.headers.get("content-type", "").startswith("application/json"):
                    error_body = resp.json()
            except Exception:
                pass

            # Extract error message
            err = error_body.get("error", {})
            if isinstance(err, dict):
                error_msg = err.get("message", "") or str(error_body)[:200]
            else:
                error_msg = str(error_body)[:200]
            err_lower = error_msg.lower()

            # Detect quota exhaustion: "exhausted", "quota", "rate limited", 429
            is_quota = (
                resp.status_code == 429
                or "exhausted" in err_lower
                or "quota" in err_lower
                or "rate limit" in err_lower
                or "limit exceeded" in err_lower
            )

            if is_quota:
                # Long backoff for exhausted quotas (1 hour)
                _record_failure(model, backoff_s=3600)
                log.warning(
                    "Alibaba %s: quota exhausted (HTTP %d). Fallback to next model (#%d).",
                    model, resp.status_code, fallback_count + 1,
                )
                fallback_count += 1
                continue

            # Other errors: model doesn't exist, bad request, etc.
            _record_failure(model)
            last_error = RuntimeError(f"[{model}] HTTP {resp.status_code}: {error_msg[:200]}")
            log.warning("Alibaba %s: API error: %s", model, error_msg[:150])
            continue

        except requests.Timeout:
            _record_failure(model)
            last_error = TimeoutError(f"[{model}] Request timeout ({timeout_s}s)")
            log.warning("Alibaba %s: timeout (%ds)", model, timeout_s)
            continue

        except Exception as e:
            _record_failure(model)
            last_error = RuntimeError(f"[{model}] {type(e).__name__}: {str(e)[:200]}")
            log.warning("Alibaba %s: %s: %s", model, type(e).__name__, str(e)[:150])
            continue

    # All models failed
    raise RuntimeError(
        f"All {len(MODEL_PRIORITY)} Alibaba models failed"
        + (f". Last error: {last_error}" if last_error else "")
    )


def get_model_status() -> dict:
    """Return health status of all models for monitoring."""
    result = {}
    for model in MODEL_PRIORITY:
        h = _get_health(model)
        result[model] = {
            "available": _is_available(model),
            "success": h["success"],
            "fail": h["fail"],
            "consecutive_fails": h["consecutive_fails"],
            "backoff_remaining_s": max(0, int(h["backoff_until"] - time.time())),
        }
    return result