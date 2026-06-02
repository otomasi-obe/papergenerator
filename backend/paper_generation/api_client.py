"""
AIOTOMASI API caller — shared low-level transport.

Exposes ``_call_aiotomasi`` (single-model SSE call) and
``_call_aiotomasi_with_fallback`` (chains primary + FALLBACK_MODELS on
transient errors). Used by ``generate_paper_chunked`` and the chat
streaming endpoint in ``app.py``.
"""

import json
import logging
import os
from pathlib import Path

import requests

from core.env_loader import load_app_env

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

load_app_env()

AIOTOMASI_API = os.getenv("AIOTOMASI_API")
AIOTOMASI_APIKEY = os.getenv("AIOTOMASI_APIKEY")
AIOTOMASI_MODEL = os.getenv("MODELGENERATE") or "VIOLA-GENERATE"


def _call_aiotomasi(
    messages: list,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float | None = None,
    progress_cb=None,
) -> str:
    """Call AIOTOMASI API via requests with SSE streaming."""
    from core.retry_helper import get_retry_config
    
    if timeout is None:
        _, timeout = get_retry_config()
    
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "max_tokens": 32000,
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=timeout, stream=True)
    resp.raise_for_status()

    content = ""
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("data: "):
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                if delta.get("content"):
                    content += delta["content"]
                    if progress_cb:
                        progress_cb(len(content))
            except json.JSONDecodeError:
                pass
        elif line.startswith("{"):
            try:
                full = json.loads(line)
                if full.get("choices"):
                    msg = full["choices"][0].get("message", {})
                    if msg.get("content"):
                        content += msg["content"]
                        if progress_cb:
                            progress_cb(len(content))
            except json.JSONDecodeError:
                pass

    if not content:
        raise ValueError("API returned empty content")

    return content


# ── Fallback model chain ──────────────────────────────────────────────────────
# Order: try the primary model first, then walk down the list. Each entry is
# attempted independently; if all fail the last exception is re-raised.
FALLBACK_MODELS = [os.getenv("MODELGENERATE") or "VIOLA-GENERATE", os.getenv("MODELCHAT") or "VIOLA-CHAT"]


def _call_aiotomasi_with_fallback(
    messages: list,
    api_key: str,
    base_url: str,
    primary_model: str,
    timeout: float | None = None,
    progress_cb=None,
) -> tuple:
    """Try primary_model first, then walk FALLBACK_MODELS on transient errors.
    Returns (content, model_used). Raises the last exception if everything fails.
    """
    from core.retry_helper import get_retry_config, retry_with_backoff
    
    if timeout is None:
        _, timeout = get_retry_config()
    
    chain = [primary_model] + [m for m in FALLBACK_MODELS if m != primary_model]
    last_err = None
    
    for idx, m in enumerate(chain):
        try:
            # Wrap each model call with retry logic
            call_fn = retry_with_backoff(
                _call_aiotomasi,
                max_retries=3,  # 3 retries per model in the chain
                retryable_exceptions=(requests.exceptions.RequestException, ValueError)
            )
            content = call_fn(
                messages, api_key, base_url, m, timeout=timeout, progress_cb=progress_cb
            )
            return content, m
        except Exception as e:
            last_err = e
            # Don't retry on auth (401/403) — those are config errors, not upstream flakiness
            err_str = str(e)
            if "401" in err_str or "403" in err_str:
                raise
            log.warning("fallback_model_failed", extra={"model": m, "error": err_str[:120]})
            continue
    raise last_err if last_err else RuntimeError("All fallback models failed")
