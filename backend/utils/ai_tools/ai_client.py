"""
Central AI Client — per-index endpoint failover.
=================================================
Single entry point for every upstream chat-completions call. Iterates the
``(model, base_url, api_key)`` chain from :func:`model_config.get_endpoint_chain`
in priority order 1→2→3. Each index uses its OWN endpoint and key, so failover
switches provider as well as model name (the MonitoringVokasi pattern).

Two public helpers:

  ``chat(messages, heavy=False, **opts) -> (content, model_used)``
      Non-streaming. Returns the assistant content string and the model that
      produced it. Raises the last exception when the whole chain fails.

  ``stream_chat(messages, heavy=False, **opts) -> Iterator[str]``
      Streaming. Yields content-delta strings. On a per-index failure BEFORE
      any token is emitted, it transparently falls through to the next index.
      Once a stream has started emitting tokens we stay on that index (a mid
      stream drop is surfaced as StopIteration / the caller's problem, matching
      how the previous single-endpoint code behaved).

``heavy=False`` selects the MODELCHAT chain; ``heavy=True`` the MODELGENERATE
chain.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterator

import requests

from utils.ai_tools.model_config import get_endpoint_chain, get_retry_count

log = logging.getLogger(__name__)

# Substrings that indicate a non-retryable upstream error → skip to next index
# immediately instead of burning retries.
_NON_RETRYABLE = ("400", "401", "403", "404")


def _is_non_retryable(err: str) -> bool:
    e = err.lower()
    return any(code in e for code in _NON_RETRYABLE)


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def chat(
    messages: list[dict[str, Any]],
    *,
    heavy: bool = False,
    max_tokens: int = 4096,
    temperature: float | None = None,
    timeout: int = 180,
    retry_count: int | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Non-streaming chat completion with per-index failover.

    Returns ``(content, model_used)``. Raises the last exception if every
    index in the chain fails.
    """
    chain = get_endpoint_chain(heavy=heavy)
    if not chain:
        raise RuntimeError(
            "ai_client.chat: no endpoint configured "
            "(set AIOTOMASI_API{1,2,3} + AIOTOMASI_APIKEY{1,2,3} + MODEL* in .env)"
        )

    max_attempts = retry_count if retry_count is not None else get_retry_count()
    last_err: Exception | None = None

    for idx, (model, base_url, api_key) in enumerate(chain, start=1):
        url = base_url + "/chat/completions"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if extra_payload:
            payload.update(extra_payload)

        delay = 2.0
        for attempt in range(1, max_attempts + 1):
            try:
                resp = requests.post(
                    url, headers=_headers(api_key), json=payload, timeout=timeout
                )
                if resp.status_code != 200:
                    raise RuntimeError(
                        f"HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError("empty choices in response")
                content = (choices[0].get("message") or {}).get("content") or ""
                log.info(
                    "ai_client.chat ok index=%d model=%s attempt=%d",
                    idx, model, attempt,
                )
                return content.strip(), model
            except Exception as e:  # noqa: BLE001
                last_err = e
                if _is_non_retryable(str(e)):
                    log.warning(
                        "ai_client.chat non-retryable index=%d model=%s: %s",
                        idx, model, e,
                    )
                    break
                if attempt >= max_attempts:
                    log.warning(
                        "ai_client.chat exhausted index=%d model=%s after %d: %s",
                        idx, model, max_attempts, e,
                    )
                    break
                log.warning(
                    "ai_client.chat retry index=%d model=%s %d/%d delay=%.1f: %s",
                    idx, model, attempt + 1, max_attempts, delay, e,
                )
                time.sleep(delay)
                delay = min(delay * 2.0, 60.0)

    raise last_err or RuntimeError("ai_client.chat: all endpoints failed")


def stream_chat(
    messages: list[dict[str, Any]],
    *,
    heavy: bool = False,
    max_tokens: int = 4096,
    temperature: float | None = None,
    timeout: int = 180,
    extra_payload: dict[str, Any] | None = None,
) -> Iterator[str]:
    """Streaming chat completion with per-index failover.

    Yields assistant content-delta strings. Falls through to the next index
    only if a connection fails BEFORE any token is emitted. Raises the last
    exception if every index fails before producing output.
    """
    chain = get_endpoint_chain(heavy=heavy)
    if not chain:
        raise RuntimeError(
            "ai_client.stream_chat: no endpoint configured "
            "(set AIOTOMASI_API{1,2,3} + AIOTOMASI_APIKEY{1,2,3} + MODEL* in .env)"
        )

    last_err: Exception | None = None

    for idx, (model, base_url, api_key) in enumerate(chain, start=1):
        url = base_url + "/chat/completions"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if extra_payload:
            payload.update(extra_payload)

        emitted = False
        try:
            resp = requests.post(
                url,
                headers=_headers(api_key),
                json=payload,
                stream=True,
                timeout=timeout,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                delta = (
                    (chunk.get("choices") or [{}])[0]
                    .get("delta", {})
                    .get("content", "")
                )
                if delta:
                    emitted = True
                    yield delta
            log.info("ai_client.stream ok index=%d model=%s", idx, model)
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            if emitted:
                # Tokens already went to the client; cannot safely retry on a
                # fresh index without duplicating output. Surface the failure.
                log.warning(
                    "ai_client.stream mid-stream drop index=%d model=%s: %s",
                    idx, model, e,
                )
                raise
            log.warning(
                "ai_client.stream failed pre-token index=%d model=%s, "
                "falling through: %s",
                idx, model, e,
            )
            continue

    raise last_err or RuntimeError("ai_client.stream_chat: all endpoints failed")
