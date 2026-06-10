"""
Model Router — Higher-level API call wrappers with built-in model fallback.
============================================================================
Wraps requests to the upstream AI API with the model chain retry/fallback
from ``model_config``.

Two main entry points:
  ``route_chat_call(**kwargs)``   → uses MODELCHAT1..3
  ``route_generate_call(**kwargs)`` → uses MODELGENERATE1..3

Each function accepts the same keyword arguments as ``requests.post``
(``json``, ``headers``, ``stream``, ``timeout``) plus an optional ``api_func``
for custom callables.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

import requests

from utils.ai_tools.model_config import (
    call_chat_with_fallback,
    call_generate_with_fallback,
    get_chat_model_chain,
    get_generate_model_chain,
    get_retry_count,
)

log = logging.getLogger(__name__)


# ── Lazy env loading ─────────────────────────────────────────────────────────

def _get_api_config():
    """Load API base/key/url from env at request time, not import time."""
    api_base = (os.getenv("AIOTOMASI_API") or "").rstrip("/")
    api_key = os.getenv("AIOTOMASI_APIKEY") or ""
    api_url = f"{api_base}/chat/completions" if api_base else ""
    return api_url, api_key



def _default_api_call(*, model: str, **kwargs: Any) -> Any:
    """Default HTTP POST to ``/chat/completions`` with the given *model*.

    ``kwargs`` are forwarded to ``requests.post`` (``json``, ``headers``,
    ``stream``, ``timeout``, etc.).
    """
    api_url, api_key = _get_api_config()
    if not api_url or not api_key:
        raise RuntimeError("AIOTOMASI_API / AIOTOMASI_APIKEY not configured")

    headers = kwargs.pop("headers", {})
    headers.setdefault("Authorization", f"Bearer {api_key}")
    headers.setdefault("Content-Type", "application/json")

    payload = kwargs.pop("json", {})
    payload.setdefault("model", model)

    timeout = kwargs.pop("timeout", 180)

    resp = requests.post(
        api_url,
        headers=headers,
        json=payload,
        timeout=timeout,
        **kwargs,
    )
    resp.raise_for_status()
    return resp


# ── Public router functions ───────────────────────────────────────────────────

def route_chat_call(
    api_func: Callable | None = None,
    retry_count: int | None = None,
    **kwargs: Any,
) -> tuple[Any, str]:
    """Call the upstream API with chat model fallback.

    Returns
    -------
    (response_or_result, model_used)
    """
    func = api_func or _default_api_call
    chain = get_chat_model_chain()
    last_err = None

    max_attempts = retry_count if retry_count is not None else get_retry_count()

    for model in chain:
        for attempt in range(1, max_attempts + 1):
            try:
                result = func(model=model, **kwargs)
                return result, model
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if any(kw in err_str for kw in ("401", "403", "400", "404")):
                    log.warning("route_chat non-retryable %s: %s", model, e)
                    break
                if attempt >= max_attempts:
                    log.warning("route_chat exhausted %s after %d attempts: %s", model, max_attempts, e)
                    break
                log.warning("route_chat retry %s %d/%d: %s", model, attempt + 1, max_attempts, e)
                import time
                time.sleep(min(2.0 * (2 ** (attempt - 1)), 60.0))

    raise last_err or RuntimeError("route_chat: all chat models failed")


def route_generate_call(
    api_func: Callable | None = None,
    retry_count: int | None = None,
    **kwargs: Any,
) -> tuple[Any, str]:
    """Call the upstream API with generation model fallback.

    Returns
    -------
    (response_or_result, model_used)
    """
    func = api_func or _default_api_call
    chain = get_generate_model_chain()
    last_err = None

    max_attempts = retry_count if retry_count is not None else get_retry_count()

    for model in chain:
        for attempt in range(1, max_attempts + 1):
            try:
                result = func(model=model, **kwargs)
                return result, model
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if any(kw in err_str for kw in ("401", "403", "400", "404")):
                    log.warning("route_generate non-retryable %s: %s", model, e)
                    break
                if attempt >= max_attempts:
                    log.warning("route_generate exhausted %s after %d attempts: %s", model, max_attempts, e)
                    break
                log.warning("route_generate retry %s %d/%d: %s", model, attempt + 1, max_attempts, e)
                import time
                time.sleep(min(2.0 * (2 ** (attempt - 1)), 60.0))

    raise last_err or RuntimeError("route_generate: all generate models failed")
