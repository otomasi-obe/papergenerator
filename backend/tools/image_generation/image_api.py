"""Image generation with API-first architecture.

Architecture:
  1. PRIMARY: Pollinations.ai / free API (fast, no browser, no cookies)
  2. FALLBACK: Gemini headless Chrome (for quality or API failure)
  3. CACHE: Deduplicate by prompt MD5 hash (never regenerate same image)

Why API-first:
  - Eliminates: cookie expiry, UI drift, browser crashes, RAM/CPU overhead
  - Speed: 3-8s per image vs 30-50s via browser
  - Scalability: HTTP concurrent vs 4 sequential browser slots
  - Reliability: REST API vs brittle DOM selectors

Fallback logic:
  - API fails (timeout, error, low quality) → automatically try next provider
  - All providers fail → fall back to Gemini headless (existing system)
  - Each provider has independent health tracking

Provider priority (configurable via env):
  1. pollinations (free, no auth, ~5 req/min)
  2. gemini_headless (existing, 4 accounts, ~8/min with cookies)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────
PROVIDER_PRIORITY = os.environ.get(
    "IMAGE_GEN_PROVIDERS", "alibaba,pollinations"
).split(",")

CACHE_DIR = Path(os.environ.get("IMAGE_GEN_CACHE_DIR", "/tmp/image_gen_cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_ENABLED = os.environ.get("IMAGE_GEN_CACHE", "1") == "1"

# ─── Provider Health Tracking ────────────────────────────────────────────
_health_lock = threading.Lock()
_provider_health: dict[str, dict] = {}


def _get_health(provider: str) -> dict:
    """Get or create health record for a provider."""
    with _health_lock:
        if provider not in _provider_health:
            _provider_health[provider] = {
                "success": 0,
                "fail": 0,
                "last_success": 0.0,
                "last_fail": 0.0,
                "consecutive_fails": 0,
                "backoff_until": 0.0,
            }
        return _provider_health[provider]


def _record_success(provider: str) -> None:
    h = _get_health(provider)
    h["success"] += 1
    h["last_success"] = time.time()
    h["consecutive_fails"] = 0
    h["backoff_until"] = 0.0


def _record_failure(provider: str, backoff_s: float = 60.0) -> None:
    h = _get_health(provider)
    h["fail"] += 1
    h["last_fail"] = time.time()
    h["consecutive_fails"] += 1
    # Exponential backoff: 60s, 120s, 240s...
    delay = min(backoff_s * (2 ** (h["consecutive_fails"] - 1)), 600)
    h["backoff_until"] = time.time() + delay
    log.info("Provider %s: fail #%d, backoff %ds", provider, h["consecutive_fails"], int(delay))


def _is_available(provider: str) -> bool:
    h = _get_health(provider)
    return time.time() >= h["backoff_until"]


# ─── Prompt Cache ────────────────────────────────────────────────────────
def _prompt_hash(prompt: str) -> str:
    """MD5 hash of normalized prompt for cache key."""
    normalized = prompt.strip().lower()
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def _get_cached(prompt: str) -> Optional[bytes]:
    """Check cache for previously generated image. Returns bytes or None."""
    if not CACHE_ENABLED:
        return None
    h = _prompt_hash(prompt)
    cache_file = CACHE_DIR / f"{h}.jpg"
    if cache_file.exists():
        log.info("Cache HIT: %s", h[:8])
        return cache_file.read_bytes()
    return None


def _set_cached(prompt: str, image_bytes: bytes) -> None:
    """Store image in cache."""
    if not CACHE_ENABLED:
        return
    try:
        h = _prompt_hash(prompt)
        cache_file = CACHE_DIR / f"{h}.jpg"
        cache_file.write_bytes(image_bytes)
        log.info("Cache STORED: %s (%d bytes)", h[:8], len(image_bytes))
    except Exception as e:
        log.warning("Cache write failed: %s", e)


# ─── Provider 1: Pollinations.ai ─────────────────────────────────────────
def _generate_pollinations(prompt: str, *, timeout_s: int = 30) -> bytes:
    """Generate image via Pollinations.ai free API.
    
    Endpoint: https://image.pollinations.ai/prompt/{url_encoded_prompt}
    Models: flux (default), turbo
    Params: width, height, seed, model, nologo
    No auth required. Free tier ~5 req/min.
    """
    import urllib.parse
    
    # Build URL with parameters for academic images (1024x1024, no logo)
    encoded = urllib.parse.quote(prompt, safe="")
    url = f"https://image.pollinations.ai/prompt/{encoded}"
    params = {
        "width": 1024,
        "height": 1024,
        "nologo": "true",
        "seed": int(hash(prompt) % 99999),  # deterministic for caching
    }
    
    log.info("Pollinations: requesting image (%d chars prompt)", len(prompt))
    resp = requests.get(url, params=params, timeout=timeout_s, stream=True)
    resp.raise_for_status()
    
    # Read image bytes
    content_type = resp.headers.get("content-type", "")
    if "image/" not in content_type:
        raise RuntimeError(
            f"Pollinations returned non-image: {content_type} ({resp.status_code})"
        )
    
    image_bytes = resp.content
    if len(image_bytes) < 1000:
        raise RuntimeError(f"Pollinations returned tiny image: {len(image_bytes)} bytes")
    
    log.info("Pollinations: got %d bytes in %.1fs", len(image_bytes), resp.elapsed.total_seconds())
    return image_bytes


# ─── Provider 2: Gemini Headless (existing system) ───────────────────────
_gemini_pool = None
_gemini_pool_lock = threading.Lock()


def _get_gemini_pool():
    """Lazy-init Gemini pool. Returns None if unavailable."""
    global _gemini_pool
    with _gemini_pool_lock:
        if _gemini_pool is not None:
            return _gemini_pool
        try:
            from tools.image_generation.CreateImageGemini import GeminiPool
            _gemini_pool = GeminiPool.from_env()
            log.info("Gemini pool initialized: %d accounts", len(_gemini_pool.accounts))
            return _gemini_pool
        except Exception as e:
            log.warning("Failed to init Gemini pool: %s", e)
            return None


def _generate_gemini(prompt: str, *, out_path: Path, timeout_s: int = 300) -> bytes:
    """Generate image via Gemini headless Chrome (existing system).
    Falls back to this when API providers fail.
    """
    pool = _get_gemini_pool()
    if pool is None:
        raise RuntimeError("Gemini pool unavailable (cookies expired or not configured)")
    
    log.info("Gemini headless: requesting image")
    res = pool.generate_image(prompt, str(out_path), generate_timeout_s=timeout_s)
    return out_path.read_bytes()


# ─── Main API ────────────────────────────────────────────────────────────
PROVIDERS = {
    "alibaba": None,  # Handled specially (needs out_path)
    "pollinations": _generate_pollinations,
    # "dalle": _generate_dalle,  # Future: add OpenAI DALL-E
    # "huggingface": _generate_hf,  # Future: add HuggingFace Inference
    "gemini": None,  # Handled specially (needs out_path)
}


def generate_image(
    prompt: str,
    out_path: str | Path,
    *,
    compress: bool = True,
    max_size_mb: float = 1.0,
    generate_timeout_s: int = 60,
) -> dict:
    """Generate an image from a text prompt.

    Flow:
      1. Check cache (same prompt → return cached image)
      2. Try providers in priority order (pollinations → gemini)
      3. Skip providers in backoff (consecutive failures)
      4. Cache successful result
      5. Compress output

    Args:
      prompt: Text description of the image to generate
      out_path: Where to save the image (jpg/png)
      compress: Whether to compress to < max_size_mb
      max_size_mb: Target max file size
      generate_timeout_s: Timeout for API calls

    Returns:
      dict with: path, provider, size, cached (bool)
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Check cache
    cached = _get_cached(prompt)
    if cached is not None:
        out_path.write_bytes(cached)
        if compress:
            _try_compress(out_path, max_size_mb)
        return {
            "path": str(out_path),
            "provider": "cache",
            "size": out_path.stat().st_size,
            "cached": True,
        }

    # 2. Try providers in priority order
    last_error: Optional[Exception] = None
    
    for provider_name in PROVIDER_PRIORITY:
        provider_name = provider_name.strip()
        
        if not _is_available(provider_name):
            h = _get_health(provider_name)
            remaining = int(h["backoff_until"] - time.time())
            log.info("Skip %s (backoff %ds remaining)", provider_name, remaining)
            continue
        
        try:
            if provider_name == "alibaba":
                from tools.image_generation.image_alibaba import generate_image as _alibaba_gen  # noqa: PLC0415
                image_bytes = _alibaba_gen(
                    prompt, str(out_path),
                    width=1024, height=1024,
                    timeout_s=generate_timeout_s,
                )
            elif provider_name == "gemini":
                image_bytes = _generate_gemini(
                    prompt, out_path=out_path, timeout_s=generate_timeout_s
                )
            elif provider_name in PROVIDERS and PROVIDERS[provider_name] is not None:
                image_bytes = PROVIDERS[provider_name](
                    prompt, timeout_s=generate_timeout_s
                )
            else:
                log.warning("Unknown provider: %s", provider_name)
                continue
            
            # Success!
            _record_success(provider_name)
            _set_cached(prompt, image_bytes)
            out_path.write_bytes(image_bytes)
            
            if compress:
                _try_compress(out_path, max_size_mb)
            
            return {
                "path": str(out_path),
                "provider": provider_name,
                "size": out_path.stat().st_size,
                "cached": False,
            }
            
        except Exception as e:
            last_error = e
            _record_failure(provider_name)
            log.warning("Provider %s failed: %s", provider_name, str(e)[:200])
            continue

    # All providers failed
    raise RuntimeError(
        f"All image providers failed. Last error: {last_error}"
    )


def _try_compress(path: Path, max_size_mb: float) -> None:
    """Compress image to target size. Best-effort, non-fatal."""
    try:
        from tools.image_generation.compress import compress_image
        compress_image(str(path), max_size_mb=max_size_mb)
    except Exception as e:
        log.warning("Compression failed (keeping raw): %s", e)


def get_provider_status() -> dict:
    """Return health status of all providers."""
    result = {}
    for name in PROVIDER_PRIORITY:
        name = name.strip()
        h = _get_health(name)
        result[name] = {
            "available": _is_available(name),
            "success": h["success"],
            "fail": h["fail"],
            "consecutive_fails": h["consecutive_fails"],
            "backoff_remaining_s": max(0, int(h["backoff_until"] - time.time())),
        }
    return result
