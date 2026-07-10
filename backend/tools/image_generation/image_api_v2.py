"""
Unified round-robin image generation via TopRouter API.

Priority: ag → cloudflare → alibaba
Round-robin across provider models with 10s timeout auto-switch.
Uses subprocess/curl for AG (large base64 responses), httpx for others.

Env:
  IMAGE_GEN_API_KEY           — required Bearer token
  IMAGE_GEN_API_URL           — upstream base URL (default https://ai.otomasi.app)
  IMAGE_GEN_PROVIDERS         — comma-separated (default ag,cloudflare,alibaba)
  IMAGE_GEN_AG_MODELS         — comma-separated AG models
  IMAGE_GEN_CF_MODELS         — comma-separated Cloudflare models
  IMAGE_GEN_ALIBABA_MODELS    — comma-separated Alibaba models
  IMAGE_GEN_TIMEOUT           — seconds per request (default 10)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Optional

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

log = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────
API_URL = os.environ.get("IMAGE_GEN_API_URL") or os.environ.get("ALIBABA_IMAGE_TOPROUTER_URL", "https://ai.otomasi.app")
API_URL = API_URL.rstrip("/")
API_KEY = os.environ.get("IMAGE_GEN_API_KEY") or os.environ.get("ALIBABA_IMAGE_TOPROUTER_KEY", "")
PROVIDERS_ENV = os.environ.get("IMAGE_GEN_PROVIDERS", "ag,cloudflare,alibaba")
TIMEOUT_S = int(os.environ.get("IMAGE_GEN_TIMEOUT", "10"))

AG_MODELS = [m.strip() for m in os.environ.get(
    "IMAGE_GEN_AG_MODELS", "ag/gemini-3.1-flash-image"
).split(",") if m.strip()]

CF_MODELS = [m.strip() for m in os.environ.get(
    "IMAGE_GEN_CF_MODELS", "cf/@cf/black-forest-labs/flux-2-klein-9b"
).split(",") if m.strip()]

ALIBABA_MODELS = [m.strip() for m in os.environ.get(
    "IMAGE_GEN_ALIBABA_MODELS", "alibaba-media/qwen-image"
).split(",") if m.strip()]

PROVIDER_MODELS = {
    "ag": AG_MODELS,
    "cloudflare": CF_MODELS,
    "alibaba": ALIBABA_MODELS,
}
PROVIDER_ORDER = [p.strip() for p in PROVIDERS_ENV.split(",") if p.strip()]

# ── State ───────────────────────────────────────────────────────────────
_lock = threading.Lock()
_cursor = {p: 0 for p in PROVIDER_ORDER}
_health: dict[str, dict] = {}


def _ensure_health(provider: str) -> dict:
    with _lock:
        if provider not in _health:
            _health[provider] = {
                "success": 0,
                "fail": 0,
                "consecutive_fails": 0,
                "backoff_until": 0.0,
            }
        return _health[provider]


def _next_model(provider: str) -> Optional[str]:
    models = [m for m in PROVIDER_MODELS.get(provider, []) if m]
    if not models:
        return None
    with _lock:
        idx = _cursor.get(provider, 0) % len(models)
        _cursor[provider] = (idx + 1) % len(models)
        return models[idx]


def _mark_success(provider: str) -> None:
    h = _ensure_health(provider)
    with _lock:
        h["success"] += 1
        h["consecutive_fails"] = 0
        h["backoff_until"] = 0.0


def _mark_failure(provider: str, backoff_s: float = 60.0) -> None:
    h = _ensure_health(provider)
    with _lock:
        h["fail"] += 1
        h["consecutive_fails"] += 1
        delay = min(backoff_s * (2 ** max(h["consecutive_fails"] - 1, 0)), 3600)
        h["backoff_until"] = time.time() + delay


def _available(provider: str) -> bool:
    return time.time() >= _ensure_health(provider)["backoff_until"]


# ── Provider-specific API calls ─────────────────────────────────────────

def _call_ag(prompt: str, model: str, timeout_s: int) -> bytes:
    """AG Gemini returns base64 JSON — use subprocess curl for reliability."""
    url = f"{API_URL}/v1/images/generations"
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
        "quality": "auto",
        "background": "auto",
        "image_detail": "high",
        "output_format": "png",
    })
    cmd = [
        "curl", "-s", "-f", "--max-time", str(timeout_s),
        "-X", "POST", url,
        "-H", f"Authorization: Bearer {API_KEY}",
        "-H", "Content-Type: application/json",
        "-d", payload,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s + 5)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr[:200]}")
    data = json.loads(result.stdout)
    images = data.get("data") or []
    if not images:
        raise RuntimeError("No image data")
    b64 = images[0].get("b64_json")
    if not b64:
        raise RuntimeError("No b64_json in response")
    return base64.b64decode(b64)


def _call_httpx(prompt: str, model: str, timeout_s: int) -> bytes:
    """CF/Alibaba: use httpx (fast, reliable)."""
    if not _HAS_HTTPX:
        # Fallback to curl
        return _call_ag(prompt, model, timeout_s)  # reuse curl logic
    url = f"{API_URL}/v1/images/generations"
    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
        "quality": "auto",
        "background": "auto",
        "image_detail": "high",
        "output_format": "png",
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=timeout_s) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        images = data.get("data") or []
        if not images:
            raise RuntimeError("No image data")
        image_url = images[0].get("url")
        b64 = images[0].get("b64_json")
        if b64:
            return base64.b64decode(b64)
        if image_url:
            img_resp = client.get(image_url)
            img_resp.raise_for_status()
            return img_resp.content
        raise RuntimeError("No image bytes")


def _call_provider(provider: str, prompt: str, model: str, timeout_s: int) -> bytes:
    if provider == "ag":
        return _call_ag(prompt, model, timeout_s)
    return _call_httpx(prompt, model, timeout_s)


# ── Public API ──────────────────────────────────────────────────────────

def generate_image(
    prompt: str,
    out_path: str | Path,
    *,
    compress: bool = True,
    max_size_mb: float = 1.0,
    generate_timeout_s: int = TIMEOUT_S,
) -> dict:
    """Generate image using API round-robin providers."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not API_KEY:
        raise RuntimeError("IMAGE_GEN_API_KEY is not set")

    attempts: list[tuple[str, str]] = []
    for provider in PROVIDER_ORDER:
        if not _available(provider):
            continue
        model = _next_model(provider)
        if model:
            attempts.append((provider, model))

    if not attempts:
        raise RuntimeError("No image providers available")

    # Try providers concurrently. Do not use ThreadPoolExecutor as a context
    # manager here: __exit__ calls shutdown(wait=True), which re-hangs on slow
    # upstream HTTP calls after our deadline fires.
    executor = ThreadPoolExecutor(max_workers=len(attempts))
    futures = {
        executor.submit(_call_provider, provider, prompt, model, generate_timeout_s): (provider, model)
        for provider, model in attempts
    }
    last_error: Optional[Exception] = None
    deadline = time.time() + max(generate_timeout_s + 10, 15)
    try:
        while futures and time.time() < deadline:
            done, not_done = wait(futures, timeout=max(1, deadline - time.time()),
                                  return_when=FIRST_COMPLETED)
            if not done:
                break
            for future in done:
                provider, model = futures.pop(future)
                try:
                    image_bytes = future.result(timeout=1)
                    if not image_bytes or len(image_bytes) < 400:
                        raise RuntimeError(f"Image too small: {len(image_bytes or b'')} bytes")

                    out.write_bytes(image_bytes)
                    if compress:
                        _try_compress(out, max_size_mb)

                    _mark_success(provider)
                    return {
                        "path": str(out),
                        "provider": provider,
                        "model": model,
                        "size": out.stat().st_size,
                        "cached": False,
                    }
                except Exception as exc:
                    last_error = exc
                    _mark_failure(provider)
                    log.warning("image_api_v2: %s/%s failed: %s", provider, model, exc)
            if not not_done:
                break
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    raise RuntimeError(f"All image providers failed. Last error: {last_error}") from last_error


def _try_compress(path: Path, max_size_mb: float) -> None:
    try:
        from tools.image_generation.compress import compress_image  # noqa: PLC0415
        compress_image(str(path), max_size_mb=max_size_mb)
    except Exception as exc:  # noqa: BLE001
        log.debug("compress skipped: %s", exc)


def get_provider_status() -> dict:
    """Return provider health + model cursor for diagnostics."""
    result = {}
    with _lock:
        for provider in PROVIDER_ORDER:
            h = _health.get(provider, {})
            result[provider] = {
                "models": PROVIDER_MODELS.get(provider, []),
                "model_cursor": _cursor.get(provider, 0),
                "success": h.get("success", 0),
                "fail": h.get("fail", 0),
                "consecutive_fails": h.get("consecutive_fails", 0),
                "backoff_remaining_s": max(0, int(h.get("backoff_until", 0.0) - time.time())),
                "available": _available(provider),
            }
    return result
