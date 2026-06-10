"""
Retry helper for AI API calls with exponential backoff.

Provides configurable retry logic for transient failures (5xx, timeouts, network errors).
Configuration via env vars:
  - AI_RETRY_COUNT: max retry attempts per model (default: 5)
  - AI_TIMEOUT_SECONDS: timeout per upstream attempt (default: 30)
"""

import logging
import os
import time
from typing import Callable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


def get_retry_config() -> tuple[int, float]:
    """Get retry configuration from environment variables.
    
    Returns:
        (retry_count, timeout_seconds)
    """
    retry_count = int(os.getenv("AI_RETRY_COUNT", "5"))
    timeout_seconds = float(os.getenv("AI_TIMEOUT_SECONDS", "30"))
    return retry_count, timeout_seconds


def retry_with_backoff(
    func: Callable[..., T],
    max_retries: int | None = None,
    initial_delay: float = 2.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
    non_retryable_keywords: tuple[str, ...] = ("401", "403", "400", "404"),
) -> Callable[..., T]:
    """Decorator/wrapper for retry with exponential backoff.
    
    Args:
        func: Function to retry
        max_retries: Max retry attempts (None = use env AI_RETRY_COUNT)
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        backoff_factor: Exponential backoff multiplier
        retryable_exceptions: Tuple of exception types to retry
        non_retryable_keywords: Error message keywords that should NOT retry
    
    Returns:
        Wrapped function with retry logic
    """
    if max_retries is None:
        max_retries, _ = get_retry_config()
    
    def wrapper(*args, **kwargs) -> T:
        last_exception = None
        delay = initial_delay
        
        for attempt in range(1, max_retries + 1):
            try:
                return func(*args, **kwargs)
            except retryable_exceptions as e:
                last_exception = e
                error_str = str(e).lower()
                
                if any(keyword in error_str for keyword in non_retryable_keywords):
                    log.error(
                        f"Non-retryable error in {func.__name__}: {e}",
                        extra={"attempt": attempt, "error": str(e)[:200]}
                    )
                    raise
                
                if attempt >= max_retries:
                    log.error(
                        f"Max attempts ({max_retries}) exceeded for {func.__name__}",
                        extra={"error": str(e)[:200]}
                    )
                    raise
                
                log.warning(
                    f"Retry {attempt + 1}/{max_retries} for {func.__name__} after {delay:.1f}s",
                    extra={"error": str(e)[:200]}
                )
                time.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)
        
        # Should never reach here, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError(f"Retry logic failed for {func.__name__}")
    
    return wrapper


def call_with_retry(
    func: Callable[..., T],
    *args,
    max_retries: int | None = None,
    **kwargs
) -> T:
    """Call a function with retry logic.
    
    Usage:
        result = call_with_retry(api_call, messages, timeout=900)
    """
    wrapped = retry_with_backoff(func, max_retries=max_retries)
    return wrapped(*args, **kwargs)
