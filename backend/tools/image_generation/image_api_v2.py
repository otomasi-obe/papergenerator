"""Image generation via ai.otomasi.app with multi-model fallback.

Tries each model in sequence until one succeeds. Logs every attempt.
Worker (worker.py) handles queueing + infinite retry on total failure.

Env:
  IMAGE_GEN_API_KEY  — Bearer token (required)
  IMAGE_GEN_API_URL  — base URL (default https://ai.otomasi.app)
  IMAGE_GEN_MODELS   — comma-separated model list (default: cx/gpt-5.5-image)
  KIE_AI_API_KEY     — Kie.ai API key for Nano Banana models (optional)

Badge-tier model mapping (tried in order until one succeeds):
  Elite:    cx/gpt-5.5-image (GPT-Image, paid) → Kie.ai Nano Banana → Cloudflare fallbacks
  Pro:      cx/gpt-5.5-image → Kie.ai Nano Banana (lite) → Cloudflare fallbacks
  Starter:  cx/gpt-5.5-image → Kie.ai Nano Banana 2 Lite → Cloudflare fallbacks
  Trial:    cx/gpt-5.5-image → Cloudflare fallbacks only

"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

API_URL = (os.environ.get("IMAGE_GEN_API_URL") or "https://ai.otomasi.app").rstrip("/")
API_KEY = os.environ.get("IMAGE_GEN_API_KEY") or ""
KIE_API_KEY = os.environ.get("KIE_AI_API_KEY") or ""

# Default fallback models (used when no badge or unknown badge)
_DEFAULT_MODELS = "cx/gpt-5.5-image"
MODELS = [m.strip() for m in os.environ.get("IMAGE_GEN_MODELS", _DEFAULT_MODELS).split(",") if m.strip()]

# Use centralized badge tier config
from config.badge_tiers import get_image_models  # noqa: PLC0415


def generate_image(
    prompt: str,
    out_path: str | Path,
    *,
    compress: bool = True,
    max_size_mb: float = 1.0,
    generate_timeout_s: int = 0,
    badge: Optional[str] = None,
) -> dict:
    """Generate image via ai.otomasi.app SSE endpoint. Multi-model fallback.

    Args:
        badge: User badge tier ('elite', 'pro', 'starter', 'trial'). If provided,
               uses tier-specific model list. Falls back to MODELS if unknown.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not API_KEY:
        raise RuntimeError("IMAGE_GEN_API_KEY is not set")

    if not KIE_API_KEY:
        log.warning("KIE_AI_API_KEY not set — Kie.ai Nano Banana models will not work")

    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx not installed")

    timeout_val = generate_timeout_s
    timeout = httpx.Timeout(timeout_val) if timeout_val else httpx.Timeout(None)

    # Select model list based on badge
    models = get_image_models(badge)
    if badge:
        log.info("image_api: badge=%s, using tier models: %s", badge, models)
    else:
        log.info("image_api: no badge, using default models: %s", models)

    last_error: Optional[str] = None

    for i, model in enumerate(models):
        attempt = i + 1
        log.info("image_api: attempt %d/%d model=%s", attempt, len(models), model)
        try:
            result = _try_model(model, prompt, out, timeout, httpx)
            if compress:
                _try_compress(out, max_size_mb)
            log.info(
                "image_api: success model=%s (%d bytes) after %d attempt(s)",
                model,
                out.stat().st_size,
                attempt,
            )
            return result
        except Exception as e:
            last_error = f"model={model}: {e}"
            log.warning(
                "image_api: attempt %d/%d model=%s FAILED: %s",
                attempt,
                len(models),
                model,
                str(e)[:300],
            )
            # Clean up partial file
            if out.exists():
                try:
                    out.unlink()
                except Exception:
                    pass

    raise RuntimeError(f"All {len(models)} models failed. Last error: {last_error}")


def _try_model(model: str, prompt: str, out: Path, timeout, httpx) -> dict:
    """Try generating with a single model. Raises on failure."""
    # Kie.ai Nano Banana models
    is_kie_nano = model in ("nano-banana", "nano-banana-2-lite", "nano-banana-edit")

    # OTOMASI Proxy models
    is_cloudflare = model.startswith("cf/@cf/")
    is_alibaba = model.startswith("alibaba-media/")

    if is_kie_nano:
        return _try_kie_nano_banana(model, prompt, out, timeout, httpx)

    url = f"{API_URL}/v1/images/generations"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    if not is_cloudflare and not is_alibaba:
        headers["Accept"] = "text/event-stream"

    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": "512x512" if is_cloudflare else "auto",
    }

    image_bytes: Optional[bytes] = None
    last_b64: Optional[str] = None

    with httpx.Client(timeout=timeout) as client:
        if is_cloudflare or is_alibaba:
            # Direct JSON response for Cloudflare and Alibaba models
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                body = resp.text[:500]
                raise RuntimeError(f"HTTP {resp.status_code}: {body}")

            data = resp.json()
            # Extract b64_json from data[0].b64_json
            if "data" in data and data["data"]:
                last_b64 = data["data"][0].get("b64_json")
        else:
            # SSE streaming for other models (GPT-Image, etc.)
            with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    body = resp.read().decode("utf-8", errors="replace")[:500]
                    raise RuntimeError(f"HTTP {resp.status_code}: {body}")

                # Parse SSE stream: collect last b64_json from any event
                current_event = None
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                    if line_str.startswith("event:"):
                        current_event = line_str[6:].strip()
                        continue
                    if line_str.startswith("data:"):
                        data_str = line_str[5:].strip()
                        if data_str == "[DONE]":
                            continue
                        try:
                            data = json.loads(data_str)
                        except (json.JSONDecodeError, ValueError):
                            log.warning("image_api: SSE parse error on line: %s", data_str[:200])
                            continue
                        log.debug(
                            "image_api: SSE event=%s data keys=%s", current_event, list(data.keys())
                        )
                        # Try multiple possible locations for b64_json
                        b64 = (
                            data.get("b64_json")  # partial_image event
                            or data.get("b64")
                            or (
                                data.get("data")
                                and isinstance(data["data"], list)
                                and data["data"][0].get("b64_json")  # done event
                            )
                        )
                        if b64:
                            last_b64 = b64
                            log.info(
                                "image_api: got b64_json from event=%s model=%s len=%d",
                                current_event,
                                model,
                                len(b64),
                            )

    if not last_b64:
        raise RuntimeError("No b64_json in response")

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


def _try_kie_nano_banana(model: str, prompt: str, out: Path, timeout, httpx) -> dict:
    """Generate image via Kie.ai (Nano Banana / Z-Image) using KieAIProvider with key pool."""
    # Map our model names to Kie.ai model identifiers
    kie_model_map = {
        "nano-banana-2-lite": "nano-banana-2-lite",
        "nano-banana": "google/nano-banana",
        "nano-banana-edit": "nano-banana-edit",
        "z-image": "z-image",
    }
    kie_model = kie_model_map.get(model, "nano-banana-2-lite")

    # Read key pool from env
    # KIE_AI_KEYS_NANO="key1,key2" for nano-banana family
    # KIE_AI_KEYS_ZIMAGE="key1,key2" for z-image
    # KIE_AI_API_KEY as fallback single key
    nano_keys_env = os.environ.get("KIE_AI_KEYS_NANO", "").strip()
    zimage_keys_env = os.environ.get("KIE_AI_KEYS_ZIMAGE", "").strip()
    fallback_key = os.environ.get("KIE_AI_API_KEY", "").strip()

    if model == "z-image":
        key_pool = [k.strip() for k in zimage_keys_env.split(",") if k.strip()]
        if not key_pool and fallback_key:
            key_pool = [fallback_key]
    else:
        key_pool = [k.strip() for k in nano_keys_env.split(",") if k.strip()]
        if not key_pool and fallback_key:
            key_pool = [fallback_key]

    if not key_pool:
        raise RuntimeError(f"No Kie.ai API key(s) configured for model {model}")

    # Use KieAIProvider with key pool
    from tools.image_generation.kie_ai_provider import KieAIProvider  # noqa: PLC0415

    provider = KieAIProvider(api_keys=key_pool)  # type: ignore[arg-type]
    return provider.generate(
        prompt=prompt,
        out_path=out,
        model=kie_model,
        aspect_ratio="1:1",
        output_format="png",
        nsfw_checker=True,
    )


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
        },
        "kie_ai": {
            "models": ["nano-banana-2-lite", "nano-banana", "nano-banana-edit"],
            "available": bool(KIE_API_KEY),
        },
    }