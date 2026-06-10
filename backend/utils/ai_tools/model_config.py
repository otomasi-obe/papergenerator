"""
Model Configuration with Retry & Fallback
==========================================
Centralised AI model resolution for chat and generation.

Supports env-var–driven model chains with per-model retry limits:

  Chat models:       MODELCHAT1 → MODELCHAT2 → MODELCHAT3
  Generation models: MODELGENERATE1 → MODELGENERATE2 → MODELGENERATE3

Each model in the chain is retried up to ``AI_RETRY_COUNT`` (default 5) times
before the next model is attempted. When every model in the chain has been
exhausted the last exception is re-raised.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

# ── Defaults ──────────────────────────────────────────────────────────────────
_DEFAULT_CHAT_MODELS = ["VIOLA-CHAT"]
_DEFAULT_GENERATE_MODELS = ["VIOLA-GENERATE"]
_DEFAULT_RETRIES = 3

# ── Model chain resolution ────────────────────────────────────────────────────

def get_chat_model_chain() -> list[str]:
    """Return the ordered list of chat models from env (MODELCHAT1..3)."""
    models = []
    for i in range(1, 4):
        m = os.getenv(f"MODELCHAT{i}")
        if m:
            models.append(m.strip())
    return models or _DEFAULT_CHAT_MODELS


def get_generate_model_chain() -> list[str]:
    """Return the ordered list of generation models from env (MODELGENERATE1..3)."""
    models = []
    for i in range(1, 4):
        m = os.getenv(f"MODELGENERATE{i}")
        if m:
            models.append(m.strip())
    return models or _DEFAULT_GENERATE_MODELS


def get_retry_count() -> int:
    """Per-model retry limit (env AI_RETRY_COUNT, default 5)."""
    try:
        return min(_DEFAULT_RETRIES, max(1, int(os.getenv("AI_RETRY_COUNT", str(_DEFAULT_RETRIES)))))
    except (TypeError, ValueError):
        return _DEFAULT_RETRIES


# ── Retry + fallback caller ───────────────────────────────────────────────────

def call_with_model_chain(
    api_func: Callable[..., T],
    model_chain: list[str],
    *,
    retry_count: int | None = None,
    initial_delay: float = 2.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    non_retryable_keywords: tuple[str, ...] = ("401", "403", "400", "404"),
    **kwargs: Any,
) -> T:
    """Call *api_func* with each model in *model_chain*.

    For each model:
      1. Call *api_func(model=m, **kwargs)*.
      2. On success → return the result immediately.
      3. On retryable exception → backoff & retry up to *retry_count* times.
      4. On non-retryable exception (auth, bad request) → skip to the next model
         immediately.
      5. When a model is exhausted → log warning and try the next model.

    If every model in the chain has been exhausted the *last* exception is
    re-raised.

    Parameters
    ----------
    api_func : callable
        The underlying API function.  It must accept a ``model`` keyword
        argument.  Additional kwargs are forwarded as-is.
    model_chain : list[str]
        Ordered model names to try.
    retry_count : int, optional
        Max retries per model.  Defaults to ``get_retry_count()``.
    initial_delay, max_delay, backoff_factor : float
        Exponential-backoff parameters.
    non_retryable_keywords : tuple[str]
        Error substrings that should NOT be retried (skip model immediately).
    **kwargs
        Forwarded to *api_func*.

    Returns
    -------
    T
        The result of *api_func* for the first successful model.

    Raises
    ------
    last_exception
        When every model in the chain has failed.
    """
    if retry_count is None:
        retry_count = get_retry_count()

    last_exception: Exception | None = None
    chain = list(model_chain)

    for idx, model in enumerate(chain):
        log.info(
            "model_chain attempt model=%s (%d/%d)",
            model,
            idx + 1,
            len(chain),
        )
        delay = initial_delay

        for attempt in range(1, retry_count + 1):
            try:
                result = api_func(model=model, **kwargs)
                log.info(
                    "model_chain success model=%s attempt=%d",
                    model,
                    attempt,
                )
                return result
            except Exception as e:
                last_exception = e
                error_str = str(e).lower()

                if any(kw in error_str for kw in non_retryable_keywords):
                    log.warning(
                        "model_chain non-retryable model=%s attempt=%d: %s",
                        model,
                        attempt,
                        e,
                    )
                    break

                if attempt >= retry_count:
                    log.warning(
                        "model_chain exhausted model=%s after %d attempts: %s",
                        model,
                        retry_count,
                        e,
                    )
                    break

                log.warning(
                    "model_chain retry model=%s attempt=%d/%d delay=%.1f: %s",
                    model,
                    attempt + 1,
                    retry_count,
                    delay,
                    e,
                )
                time.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)

    # All models exhausted
    if last_exception is not None:
        raise last_exception
    raise RuntimeError("model_chain: empty model chain")


# ── Convenience wrappers ─────────────────────────────────────────────────────

def call_chat_with_fallback(
    api_func: Callable[..., T],
    *,
    retry_count: int | None = None,
    **kwargs: Any,
) -> T:
    """Call *api_func* with MODELCHAT1 → MODELCHAT2 → MODELCHAT3 fallback."""
    chain = get_chat_model_chain()
    return call_with_model_chain(
        api_func,
        chain,
        retry_count=retry_count,
        **kwargs,
    )


def call_generate_with_fallback(
    api_func: Callable[..., T],
    *,
    retry_count: int | None = None,
    **kwargs: Any,
) -> T:
    """Call *api_func* with MODELGENERATE1 → MODELGENERATE2 → MODELGENERATE3 fallback."""
    chain = get_generate_model_chain()
    return call_with_model_chain(
        api_func,
        chain,
        retry_count=retry_count,
        **kwargs,
    )


# ── Direct model lookups (for logging / display purposes) ────────────────────

def get_primary_chat_model() -> str:
    """Return the first configured chat model (or fallback default)."""
    chain = get_chat_model_chain()
    return chain[0]


def get_primary_generate_model() -> str:
    """Return the first configured generation model (or fallback default)."""
    chain = get_generate_model_chain()
    return chain[0]
