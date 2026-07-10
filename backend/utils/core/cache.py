"""
Simple in-memory cache for static/rarely-changing data.
Reduces database load for frequently accessed data like topics, styles, journals.
"""
import threading
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Optional

_cache_lock = threading.Lock()
_cache_store: dict[str, tuple[Any, datetime]] = {}
# Per-key locks serialize concurrent cold-cache calls so the wrapped function
# runs once per key (single-flight), preventing a cache stampede under load.
_keyed_locks: dict[str, threading.Lock] = {}
_keyed_locks_guard = threading.Lock()
_MAX_KEYED_LOCKS = 500

# Max entries to prevent memory leak from unbounded growth
_MAX_CACHE_ENTRIES = 500
_cleanup_interval = 100  # Cleanup every N accesses
_access_count = 0


def _evict_expired():
    """Remove all expired entries from cache. Must be called with _cache_lock held."""
    now = datetime.now()
    expired = [k for k, (_, exp) in _cache_store.items() if now >= exp]
    for k in expired:
        del _cache_store[k]
    # If still over limit, evict oldest entries
    if len(_cache_store) > _MAX_CACHE_ENTRIES:
        sorted_keys = sorted(_cache_store.keys(), key=lambda k: _cache_store[k][1])
        for k in sorted_keys[:len(_cache_store) - _MAX_CACHE_ENTRIES]:
            del _cache_store[k]


def _get_key_lock(cache_key: str) -> threading.Lock:
    with _keyed_locks_guard:
        # Cleanup if over limit
        if len(_keyed_locks) > _MAX_KEYED_LOCKS:
            # Remove locks not currently held (safe heuristic)
            to_remove = [k for k, l in _keyed_locks.items() if not l.locked()]
            for k in to_remove[:len(_keyed_locks) - _MAX_KEYED_LOCKS // 2]:
                del _keyed_locks[k]
        lock = _keyed_locks.get(cache_key)
        if lock is None:
            lock = threading.Lock()
            _keyed_locks[cache_key] = lock
        return lock


def cached(ttl_seconds: int = 300):
    """Decorator to cache function results for ttl_seconds.

    Concurrent calls for the same key are single-flighted: the wrapped function
    executes once and the other callers wait for and reuse that result.

    Args:
        ttl_seconds: Time to live in seconds (default 5 minutes)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__module__}.{func.__name__}:{args}:{sorted(kwargs.items())}"

            # Fast path: serve a fresh cached value without taking the key lock.
            with _cache_lock:
                if cache_key in _cache_store:
                    value, expires_at = _cache_store[cache_key]
                    if datetime.now() < expires_at:
                        return value
                    else:
                        del _cache_store[cache_key]

            # Slow path: single-flight on a per-key lock so only one caller runs
            # the function while the others wait and reuse the result.
            key_lock = _get_key_lock(cache_key)
            with key_lock:
                # Re-check: another thread may have populated the cache while we
                # were waiting for the key lock.
                with _cache_lock:
                    if cache_key in _cache_store:
                        value, expires_at = _cache_store[cache_key]
                        if datetime.now() < expires_at:
                            return value
                        else:
                            del _cache_store[cache_key]

                result = func(*args, **kwargs)

                with _cache_lock:
                    _cache_store[cache_key] = (result, datetime.now() + timedelta(seconds=ttl_seconds))
                    # Periodic cleanup to prevent memory leak
                    global _access_count
                    _access_count += 1
                    if _access_count >= _cleanup_interval:
                        _access_count = 0
                        _evict_expired()

            return result
        return wrapper
    return decorator


def invalidate_cache(pattern: Optional[str] = None):
    """Invalidate cache entries matching pattern, or all if pattern is None."""
    with _cache_lock:
        if pattern is None:
            _cache_store.clear()
        else:
            keys_to_delete = [k for k in _cache_store.keys() if pattern in k]
            for k in keys_to_delete:
                del _cache_store[k]


def get_cache_stats() -> dict:
    """Return cache statistics."""
    with _cache_lock:
        now = datetime.now()
        valid_entries = sum(1 for _, expires_at in _cache_store.values() if expires_at > now)
        return {
            "total_entries": len(_cache_store),
            "valid_entries": valid_entries,
            "expired_entries": len(_cache_store) - valid_entries,
        }
