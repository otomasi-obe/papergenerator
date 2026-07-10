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

from utils.core.env_loader import load_app_env
from utils.ai_tools.model_config import get_generate_model_chain, get_retry_count

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

load_app_env()

AIOTOMASI_API = os.getenv("AIOTOMASI_API")
AIOTOMASI_APIKEY = os.getenv("AIOTOMASI_APIKEY")


def _call_aiotomasi(
    messages: list,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float | None = None,
    progress_cb=None,
) -> str:
    """Call AIOTOMASI API via requests with SSE streaming."""
    from utils.core.retry_helper import get_retry_config
    
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
        "max_tokens": 120000,
        "reasoning": {"effort": "high"},
    }

    with requests.post(url, json=payload, headers=headers, timeout=timeout, stream=True) as resp:
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


# ── Fallback model chain (MODELGENERATE1 → MODELGENERATE2 → MODELGENERATE3) ──
# Each model is retried up to AI_RETRY_COUNT (default 5) times before
# falling through to the next model in the chain.
_RETRY_COUNT = get_retry_count()
_MODEL_CHAIN = get_generate_model_chain()


def _call_aiotomasi_with_fallback(
    messages: list,
    api_key: str,
    base_url: str,
    primary_model: str | None = None,
    timeout: float | None = None,
    progress_cb=None,
) -> tuple:
    """Try each index in the generation endpoint chain with retry.

    Uses the per-index chain (MODELGENERATE1..3, each paired with its OWN
    AIOTOMASI_API{i}/AIOTOMASI_APIKEY{i}). Each index gets up to AI_RETRY_COUNT
    retries; falls through to the next index when one is exhausted. The
    ``api_key``/``base_url`` arguments are used only as a fallback when no
    indexed endpoint resolves (legacy single-endpoint callers).
    Returns (content, model_used). Raises the last exception if everything fails.
    """
    from utils.core.retry_helper import get_retry_config, retry_with_backoff
    from utils.ai_tools.model_config import get_endpoint_chain

    if timeout is None:
        _, timeout = get_retry_config()

    # Each entry: (model, base_url, api_key) — per-index endpoint+key.
    chain = get_endpoint_chain(heavy=True)
    if not chain and base_url and api_key:
        # Legacy fallback: caller-supplied single endpoint with the model chain.
        chain = [(m, base_url, api_key) for m in get_generate_model_chain()]

    last_err = None

    for idx, (m, b_url, b_key) in enumerate(chain):
        log.info("api_client attempt index=%d model=%s base=%s", idx + 1, m, b_url)
        try:
            call_fn = retry_with_backoff(
                _call_aiotomasi,
                max_retries=_RETRY_COUNT,
                retryable_exceptions=(requests.exceptions.RequestException, ValueError)
            )
            content = call_fn(
                messages, b_key, b_url, m,
                timeout=timeout, progress_cb=progress_cb
            )
            log.info("api_client success index=%d model=%s", idx + 1, m)
            return content, m
        except Exception as e:
            last_err = e
            err_str = str(e)
            if "401" in err_str or "403" in err_str:
                # Auth failure is endpoint-specific; try the next index rather
                # than aborting the whole chain.
                log.warning("api_client auth error index=%d model=%s: %s", idx + 1, m, err_str[:120])
                continue
            log.warning("api_client exhausted index=%d model=%s: %s", idx + 1, m, err_str[:120])
            continue
    raise last_err if last_err else RuntimeError("All fallback endpoints failed")
