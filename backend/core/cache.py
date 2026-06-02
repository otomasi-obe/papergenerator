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


def cached(ttl_seconds: int = 300):
    """Decorator to cache function results for ttl_seconds.

    Args:
        ttl_seconds: Time to live in seconds (default 5 minutes)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__module__}.{func.__name__}:{args}:{sorted(kwargs.items())}"

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
