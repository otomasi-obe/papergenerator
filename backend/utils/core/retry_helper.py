"""
Retry helper for AI API calls with exponential backoff and circuit breaker.

Provides configurable retry logic for transient failures (5xx, timeouts, network errors).
Configuration via env vars:
  - AI_RETRY_COUNT: max retry attempts per model (default: 5)
  - AI_TIMEOUT_SECONDS: timeout per upstream attempt (default: 30)
"""

import logging
import os
import time
import threading
from typing import Callable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


def get_retry_config() -> tuple[int, float]:
    """Get retry configuration from environment variables.
    
    Returns:
        (retry_count, timeout_seconds)
    """
    retry_count = int(os.getenv("AI_RETRY_COUNT", "5"))
    timeout_seconds = float(os.getenv("AI_TIMEOUT_SECONDS", "1800"))
    return retry_count, timeout_seconds


# ── Circuit Breaker ──────────────────────────────────────────────────────────

class CircuitBreaker:
    """Simple circuit breaker to prevent hammering a failing API.
    
    States:
        CLOSED   — normal operation, calls pass through.
        OPEN     — failures exceeded threshold, calls fail-fast immediately.
        HALF-OPEN — after cooldown, allow one probe call to test recovery.
    
    Configuration:
        failure_threshold: consecutive failures before opening (default 5)
        recovery_timeout:  seconds to wait before trying again (default 60)
    """
    
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()
    
    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = self.HALF_OPEN
            return self._state
    
    def record_success(self):
        with self._lock:
            self._failure_count = 0
            self._state = self.CLOSED
    
    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                self._state = self.OPEN
                log.warning(
                    "Circuit breaker OPEN after %d failures, recovery in %.0fs",
                    self._failure_count, self.recovery_timeout,
                )
    
    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        s = self.state  # triggers half_open transition if cooldown elapsed
        return s in (self.CLOSED, self.HALF_OPEN)


# Global circuit breakers per endpoint/model
_circuit_breakers: dict[str, CircuitBreaker] = {}
_cb_lock = threading.Lock()


def get_circuit_breaker(key: str, failure_threshold: int = 5, recovery_timeout: float = 60.0) -> CircuitBreaker:
    """Get or create a circuit breaker for the given key (e.g. model name or endpoint)."""
    with _cb_lock:
        if key not in _circuit_breakers:
            _circuit_breakers[key] = CircuitBreaker(
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
            )
        return _circuit_breakers[key]


class CircuitBreakerOpen(Exception):
    """Raised when a circuit breaker blocks a request."""
    pass


def retry_with_backoff(
    func: Callable[..., T],
    max_retries: int | None = None,
    initial_delay: float = 2.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
    non_retryable_keywords: tuple[str, ...] = ("401", "403", "400", "404"),
    circuit_breaker_key: str | None = None,
) -> Callable[..., T]:
    """Decorator/wrapper for retry with exponential backoff and optional circuit breaker.
    
    Args:
        func: Function to retry
        max_retries: Max retry attempts (None = use env AI_RETRY_COUNT)
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        backoff_factor: Exponential backoff multiplier
        retryable_exceptions: Tuple of exception types to retry
        non_retryable_keywords: Error message keywords that should NOT retry
        circuit_breaker_key: If set, uses a circuit breaker with this key to
            prevent hammering a failing endpoint.
    
    Returns:
        Wrapped function with retry logic
    """
    if max_retries is None:
        max_retries, _ = get_retry_config()
    
    # Get or create circuit breaker if key provided
    cb = get_circuit_breaker(circuit_breaker_key) if circuit_breaker_key else None
    
    def wrapper(*args, **kwargs) -> T:
        # Circuit breaker check: fail-fast if endpoint is down
        if cb and not cb.allow_request():
            raise CircuitBreakerOpen(
                f"Circuit breaker OPEN for {circuit_breaker_key}. "
                f"Endpoint temporarily unavailable. Try again later."
            )
        
        last_exception = None
        delay = initial_delay
        
        for attempt in range(1, max_retries + 1):
            try:
                result = func(*args, **kwargs)
                # Success — reset circuit breaker
                if cb:
                    cb.record_success()
                return result
            except CircuitBreakerOpen:
                raise
            except retryable_exceptions as e:
                last_exception = e
                error_str = str(e).lower()
                
                if any(keyword in error_str for keyword in non_retryable_keywords):
                    log.error(
                        f"Non-retryable error in {func.__name__}: {e}",
                        extra={"attempt": attempt, "error": str(e)[:200]}
                    )
                    # Don't record failure for non-retryable errors — 
                    # client errors shouldn't trip the circuit breaker
                    raise
                
                if attempt >= max_retries:
                    log.error(
                        f"Max attempts ({max_retries}) exceeded for {func.__name__}",
                        extra={"error": str(e)[:200]}
                    )
                    if cb:
                        cb.record_failure()
                    raise
                
                # Add jitter to avoid thundering herd under high concurrency
                import random
                jitter = random.uniform(0, delay * 0.25)
                sleep_time = delay + jitter
                
                log.warning(
                    f"Retry {attempt + 1}/{max_retries} for {func.__name__} after {sleep_time:.1f}s",
                    extra={"error": str(e)[:200]}
                )
                time.sleep(sleep_time)
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
    circuit_breaker_key: str | None = None,
    **kwargs
) -> T:
    """Call a function with retry logic and optional circuit breaker.
    
    Usage:
        result = call_with_retry(api_call, messages, timeout=900)
        result = call_with_retry(api_call, messages, timeout=900,
                                 circuit_breaker_key="generate_model_1")
    """
    wrapped = retry_with_backoff(
        func, max_retries=max_retries, circuit_breaker_key=circuit_breaker_key
    )
    return wrapped(*args, **kwargs)
