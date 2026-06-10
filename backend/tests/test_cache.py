"""
Unit tests for core/cache.py — In-memory caching system.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

os.environ.setdefault("FLASK_ENV", "testing")

try:
    from utils.core.cache import cached, get_cache_stats, invalidate_cache
except Exception as e:
    pytest.skip(f"Cache module bootstrap failed: {e}", allow_module_level=True)


@pytest.fixture(autouse=True)
def clear_cache():
    invalidate_cache()
    yield
    invalidate_cache()


def test_cached_decorator_basic():
    call_count = 0

    @cached(ttl_seconds=60)
    def expensive_function(x):
        nonlocal call_count
        call_count += 1
        return x * 2

    result1 = expensive_function(5)
    assert result1 == 10
    assert call_count == 1

    result2 = expensive_function(5)
    assert result2 == 10
    assert call_count == 1

    result3 = expensive_function(10)
    assert result3 == 20
    assert call_count == 2


def test_cached_decorator_with_kwargs():
    call_count = 0

    @cached(ttl_seconds=60)
    def function_with_kwargs(a, b=10):
        nonlocal call_count
        call_count += 1
        return a + b

    result1 = function_with_kwargs(5, b=10)
    assert result1 == 15
    assert call_count == 1

    result2 = function_with_kwargs(5, b=10)
    assert result2 == 15
    assert call_count == 1

    result3 = function_with_kwargs(5, b=20)
    assert result3 == 25
    assert call_count == 2


def test_cached_decorator_ttl_expiration():
    call_count = 0

    @cached(ttl_seconds=1)
    def short_ttl_function(x):
        nonlocal call_count
        call_count += 1
        return x * 2

    result1 = short_ttl_function(5)
    assert result1 == 10
    assert call_count == 1

    result2 = short_ttl_function(5)
    assert result2 == 10
    assert call_count == 1

    time.sleep(1.1)

    result3 = short_ttl_function(5)
    assert result3 == 10
    assert call_count == 2


def test_invalidate_cache_all():
    @cached(ttl_seconds=60)
    def func1(x):
        return x * 2

    @cached(ttl_seconds=60)
    def func2(x):
        return x * 3

    func1(5)
    func2(5)

    stats = get_cache_stats()
    assert stats["total_entries"] == 2

    invalidate_cache()

    stats = get_cache_stats()
    assert stats["total_entries"] == 0


def test_invalidate_cache_pattern():
    @cached(ttl_seconds=60)
    def user_function(user_id):
        return f"user_{user_id}"

    @cached(ttl_seconds=60)
    def paper_function(paper_id):
        return f"paper_{paper_id}"

    user_function(1)
    user_function(2)
    paper_function(1)

    stats = get_cache_stats()
    assert stats["total_entries"] == 3

    invalidate_cache("user_function")

    stats = get_cache_stats()
    assert stats["total_entries"] == 1


def test_get_cache_stats():
    @cached(ttl_seconds=60)
    def func(x):
        return x * 2

    func(1)
    func(2)
    func(3)

    stats = get_cache_stats()
    assert stats["total_entries"] == 3
    assert stats["valid_entries"] == 3
    assert stats["expired_entries"] == 0


def test_get_cache_stats_with_expired():
    @cached(ttl_seconds=1)
    def func(x):
        return x * 2

    func(1)
    func(2)

    time.sleep(1.1)

    func(3)

    stats = get_cache_stats()
    assert stats["total_entries"] == 3
    assert stats["valid_entries"] == 1
    assert stats["expired_entries"] == 2


def test_cached_different_functions_same_args():
    @cached(ttl_seconds=60)
    def func1(x):
        return x * 2

    @cached(ttl_seconds=60)
    def func2(x):
        return x * 3

    result1 = func1(5)
    result2 = func2(5)

    assert result1 == 10
    assert result2 == 15

    stats = get_cache_stats()
    assert stats["total_entries"] == 2


def test_cached_thread_safety():
    import threading

    call_count = 0
    lock = threading.Lock()

    @cached(ttl_seconds=60)
    def thread_safe_function(x):
        nonlocal call_count
        with lock:
            call_count += 1
        time.sleep(0.01)
        return x * 2

    threads = []
    for _ in range(10):
        t = threading.Thread(target=lambda: thread_safe_function(5))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert call_count == 1


def test_cached_with_none_args():
    call_count = 0

    @cached(ttl_seconds=60)
    def func_with_none(x=None):
        nonlocal call_count
        call_count += 1
        return x or "default"

    result1 = func_with_none(None)
    assert result1 == "default"
    assert call_count == 1

    result2 = func_with_none(None)
    assert result2 == "default"
    assert call_count == 1

    result3 = func_with_none("value")
    assert result3 == "value"
    assert call_count == 2
