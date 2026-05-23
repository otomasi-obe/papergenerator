"""
AIOTOMASI API caller — shared low-level transport.

Exposes ``_call_aiotomasi`` (single-model SSE call) and
``_call_aiotomasi_with_fallback`` (chains primary + FALLBACK_MODELS on
transient errors). Used by ``generate_paper_chunked`` and the chat
streaming endpoint in ``app.py``.
"""

import os
import json
from pathlib import Path
from core.env_loader import load_app_env
import requests

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

load_app_env()

AIOTOMASI_API    = os.getenv("AIOTOMASI_API")
AIOTOMASI_APIKEY = os.getenv("AIOTOMASI_APIKEY")
AIOTOMASI_MODEL  = os.getenv("AIOTOMASI_MODEL", "V-OPUS")


def _call_aiotomasi(messages: list, api_key: str, base_url: str, model: str, timeout: float = 900.0, progress_cb=None) -> str:
    """Call AIOTOMASI API via requests with SSE streaming."""
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
FALLBACK_MODELS = ["V-OPUS", "V-DEEPSEEK"]


def _call_aiotomasi_with_fallback(messages: list, api_key: str, base_url: str, primary_model: str, timeout: float = 900.0, progress_cb=None) -> tuple:
    """Try primary_model first, then walk FALLBACK_MODELS on transient errors.
    Returns (content, model_used). Raises the last exception if everything fails.
    """
    chain = [primary_model] + [m for m in FALLBACK_MODELS if m != primary_model]
    last_err = None
    for idx, m in enumerate(chain):
        try:
            content = _call_aiotomasi(messages, api_key, base_url, m, timeout=timeout, progress_cb=progress_cb)
            return content, m
        except Exception as e:
            last_err = e
            # Don't retry on auth (401/403) — those are config errors, not upstream flakiness
            err_str = str(e)
            if "401" in err_str or "403" in err_str:
                raise
            print(f"[fallback] model={m} failed ({err_str[:120]}); trying next…", flush=True)
            continue
    raise last_err if last_err else RuntimeError("All fallback models failed")
