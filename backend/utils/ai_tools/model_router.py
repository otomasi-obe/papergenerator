"""
Model Router — Higher-level API call wrappers with built-in endpoint failover
and circuit breaker protection.
============================================================================
Wraps requests to the upstream AI API with the per-index endpoint chain from
``model_config.get_endpoint_chain``. Each index carries its OWN
``(model, base_url, api_key)`` triple, so failover 1→2→3 switches provider as
well as model name (the MonitoringVokasi pattern).

Circuit breaker per endpoint prevents hammering a failing upstream.

Two main entry points:
  ``route_chat_call(**kwargs)``     → uses MODELCHAT1..3   + matching endpoints
  ``route_generate_call(**kwargs)`` → uses MODELGENERATE1..3 + matching endpoints

Each returns ``(requests.Response, model_used)``. The Response is the raw
upstream response (callers use ``.json()`` or ``.iter_lines()`` as before).
Keyword arguments are forwarded to ``requests.post`` (``json``, ``headers``,
``stream``, ``timeout``).
"""

from __future__ import annotations

import logging
import random
import re
import time
from typing import Any, Callable

import requests

from utils.ai_tools.model_config import (
    get_endpoint_chain,
    get_retry_count,
)
from utils.core.retry_helper import CircuitBreaker, get_circuit_breaker

log = logging.getLogger(__name__)


def _default_api_call(
    *, model: str, base_url: str, api_key: str, **kwargs: Any
) -> requests.Response:
    """POST to ``{base_url}/chat/completions`` with the given model+key.

    ``kwargs`` are forwarded to ``requests.post`` (``json``, ``headers``,
    ``stream``, ``timeout``, etc.).
    """
    if not base_url or not api_key:
        raise RuntimeError("route: endpoint base_url / api_key not configured")

    api_url = base_url.rstrip("/") + "/chat/completions"

    headers = kwargs.pop("headers", {}) or {}
    headers.setdefault("Authorization", f"Bearer {api_key}")
    headers.setdefault("Content-Type", "application/json")

    payload = kwargs.pop("json", {}) or {}
    payload.setdefault("model", model)

    timeout = kwargs.pop("timeout", 180)

    # SSL verify: skip if env var set (upstream cert may be self-signed/expired)
    verify = kwargs.pop("verify", None)
    if verify is None:
        import os as _os
        verify = _os.getenv("AI_SSL_VERIFY", "true").lower() not in ("false", "0", "no")

    resp = requests.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=timeout,
        verify=verify,
        **kwargs,
    )
    resp.raise_for_status()
    return resp


def _route(
    chain: list[tuple[str, str, str]],
    api_func: Callable | None,
    retry_count: int | None,
    label: str,
    **kwargs: Any,
) -> tuple[Any, str]:
    """Shared failover loop over a ``(model, base_url, api_key)`` chain.
    
    Each endpoint gets its own circuit breaker. If an endpoint's breaker is
    open, we skip it immediately and try the next endpoint in the chain.
    """
    if not chain:
        raise RuntimeError(
            f"{label}: no endpoint configured "
            "(set AIOTOMASI_API{1,2,3} + AIOTOMASI_APIKEY{1,2,3} + MODEL* in .env)"
        )

    func = api_func or _default_api_call
    max_attempts = retry_count if retry_count is not None else get_retry_count()
    last_err: Exception | None = None

    for idx, (model, base_url, api_key) in enumerate(chain, start=1):
        # Per-endpoint circuit breaker (keyed by base_url to handle same endpoint
        # with different models)
        cb_key = f"{label}:{base_url}"
        cb = get_circuit_breaker(cb_key, failure_threshold=5, recovery_timeout=60.0)
        
        if not cb.allow_request():
            log.warning(
                "%s circuit breaker OPEN for index=%d %s, skipping",
                label, idx, model,
            )
            continue
        
        for attempt in range(1, max_attempts + 1):
            try:
                result = func(
                    model=model, base_url=base_url, api_key=api_key, **kwargs
                )
                cb.record_success()
                return result, model
            except Exception as e:  # noqa: BLE001
                last_err = e
                err_str = str(e).lower()
                if re.search(r"\b(40[0134])\b", err_str):
                    log.warning("%s non-retryable index=%d %s: %s", label, idx, model, e)
                    cb.record_failure()
                    break
                if attempt >= max_attempts:
                    log.warning(
                        "%s exhausted index=%d %s after %d attempts: %s",
                        label, idx, model, max_attempts, e,
                    )
                    cb.record_failure()
                    break
                # Exponential backoff with jitter to avoid thundering herd
                base_delay = min(2.0 * (2 ** (attempt - 1)), 60.0)
                jitter = random.uniform(0, base_delay * 0.25)
                sleep_time = base_delay + jitter
                log.warning(
                    "%s retry index=%d %s %d/%d in %.1fs: %s",
                    label, idx, model, attempt + 1, max_attempts, sleep_time, e,
                )
                time.sleep(sleep_time)

    raise last_err or RuntimeError(f"{label}: all endpoints failed")


# ── Public router functions ───────────────────────────────────────────────────

def route_chat_call(
    api_func: Callable | None = None,
    retry_count: int | None = None,
    **kwargs: Any,
) -> tuple[Any, str]:
    """Call the upstream API with chat endpoint chain fallback (MODELCHAT1..3).

    Returns ``(response_or_result, model_used)``.
    """
    return _route(
        get_endpoint_chain(heavy=False),
        api_func, retry_count, "route_chat", **kwargs,
    )


def route_image_call(
    messages: list[dict],
    *,
    timeout: int = 120,
    max_retries: int = 3,
    **kwargs: Any,
) -> tuple[Any, str]:
    """Call the upstream API for image analysis (MODELIMAGE).

    Uses a single endpoint from ``get_image_endpoint()`` — no failover chain
    since image models are typically a dedicated vision endpoint.

    ``messages`` follows OpenAI multimodal format with ``image_url`` content parts.
    Returns ``(response, model_used)``.

    Includes retry logic with exponential backoff for transient failures.
    """
    from utils.ai_tools.model_config import get_image_endpoint
    import time

    model, base_url, api_key = get_image_endpoint()
    if not base_url or not api_key:
        raise RuntimeError("route_image: MODELIMAGE endpoint not configured")

    api_url = base_url.rstrip("/") + "/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": kwargs.pop("max_tokens", 2048),
        "stream": False,
    }

    import os as _os
    verify = _os.getenv("AI_SSL_VERIFY", "true").lower() not in ("false", "0", "no")

    # Remove stream from kwargs to prevent override
    kwargs.pop("stream", None)

    last_exception = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=timeout,
                verify=verify,
                **kwargs,
            )
            resp.raise_for_status()
            return resp, model
        except requests.exceptions.RequestException as e:
            last_exception = e
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) + 1  # Exponential backoff: 1s, 3s, 5s
                log.warning("Image API call failed (attempt %d/%d), retrying in %ds: %s",
                           attempt + 1, max_retries, wait_time, e)
                time.sleep(wait_time)

    # All retries exhausted
    raise RuntimeError(f"Image API call failed after {max_retries} attempts: {last_exception}")


def route_generate_call(
    api_func: Callable | None = None,
    retry_count: int | None = None,
    **kwargs: Any,
) -> tuple[Any, str]:
    """Call the upstream API with generation endpoint chain fallback (MODELGENERATE1..3).

    Returns ``(response_or_result, model_used)``.
    """
    return _route(
        get_endpoint_chain(heavy=True),
        api_func, retry_count, "route_generate", **kwargs,
    )
