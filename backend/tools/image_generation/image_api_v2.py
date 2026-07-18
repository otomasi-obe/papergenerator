"""Image generation via ai.otomasi.app with multi-model fallback.

Tries each model in sequence until one succeeds. Logs every attempt.
Worker (worker.py) handles queueing + infinite retry on total failure.

Env:
  IMAGE_GEN_API_KEY  — Bearer token (required)
  IMAGE_GEN_API_URL  — base URL (default https://ai.otomasi.app)
  IMAGE_GEN_MODELS   — comma-separated model list (default: cx/gpt-5.5-image,ag/gemini-3.1-flash-image,alibaba-media/wan2.6-t2i)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

API_URL = (os.environ.get("IMAGE_GEN_API_URL") or "https://ai.otomasi.app").rstrip("/")
API_KEY = os.environ.get("IMAGE_GEN_API_KEY") or ""

# Multi-model fallback list — tried in order until one succeeds
_DEFAULT_MODELS = "cx/gpt-5.5-image,ag/gemini-3.1-flash-image,alibaba-media/wan2.6-t2i"
MODELS = [m.strip() for m in os.environ.get("IMAGE_GEN_MODELS", _DEFAULT_MODELS).split(",") if m.strip()]

# ponytail: no timeout — user requirement. API can take minutes for complex prompts.
_TIMEOUT = int(os.environ.get("IMAGE_GEN_TIMEOUT_S", "0")) or None


def generate_image(
    prompt: str,
    out_path: str | Path,
    *,
    compress: bool = True,
    max_size_mb: float = 1.0,
    generate_timeout_s: int = 0,
) -> dict:
    """Generate image via ai.otomasi.app SSE endpoint. Multi-model fallback."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not API_KEY:
        raise RuntimeError("IMAGE_GEN_API_KEY is not set")

    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx not installed")

    timeout_val = generate_timeout_s or _TIMEOUT
    timeout = httpx.Timeout(timeout_val) if timeout_val else httpx.Timeout(None)

    last_error: Optional[str] = None

    for i, model in enumerate(MODELS):
        attempt = i + 1
        log.info("image_api: attempt %d/%d model=%s", attempt, len(MODELS), model)
        try:
            result = _try_model(model, prompt, out, timeout, httpx)
            if compress:
                _try_compress(out, max_size_mb)
            log.info("image_api: success model=%s (%d bytes) after %d attempt(s)", model, out.stat().st_size, attempt)
            return result
        except Exception as e:
            last_error = f"model={model}: {e}"
            log.warning("image_api: attempt %d/%d model=%s FAILED: %s", attempt, len(MODELS), model, str(e)[:300])
            # Clean up partial file
            if out.exists():
                try:
                    out.unlink()
                except Exception:
                    pass

    raise RuntimeError(f"All {len(MODELS)} models failed. Last error: {last_error}")


def _try_model(model: str, prompt: str, out: Path, timeout, httpx) -> dict:
    """Try generating with a single model. Raises on failure."""
    url = f"{API_URL}/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": "auto",
        "quality": "auto",
        "background": "auto",
        "image_detail": "high",
        "output_format": "png",
    }

    image_bytes: Optional[bytes] = None

    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code != 200:
                body = resp.read().decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"HTTP {resp.status_code}: {body}")

            # Parse SSE stream: collect last b64_json from any event
            last_b64: Optional[str] = None
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    try:
                        data = json.loads(data_str)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    b64 = data.get("b64_json")
                    if b64:
                        last_b64 = b64

    if not last_b64:
        raise RuntimeError("No b64_json in SSE response")

    image_bytes = base64.b64decode(last_b64)
    if not image_bytes or len(image_bytes) < 400:
        raise RuntimeError(f"Image too small: {len(image_bytes or b'')} bytes")

    out.write_bytes(image_bytes)
    log.info("image_api: generated %s (%d bytes) model=%s", out.name, len(image_bytes), model)
    return {
        "path": str(out),
        "provider": "otomasi",
        "model": model,
        "size": out.stat().st_size,
        "cached": False,
    }


def _try_compress(path: Path, max_size_mb: float) -> None:
    try:
        from tools.image_generation.compress import compress_image  # noqa: PLC0415
        compress_image(str(path), max_size_mb=max_size_mb)
    except Exception as exc:  # noqa: BLE001
        log.debug("compress skipped: %s", exc)


def get_provider_status() -> dict:
    """Return provider health for diagnostics."""
    return {
        "otomasi": {
            "models": MODELS,
            "model_cursor": 0,
            "success": 0,
            "fail": 0,
            "consecutive_fails": 0,
            "backoff_remaining_s": 0,
            "available": True,
        }
    }
