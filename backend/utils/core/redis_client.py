"""
Shared Redis client for the PaperFull backend.

Provides a lazy-initialized Redis connection used by distributed locks,
distributed semaphores, circuit breakers, and any future cross-worker
coordination. Falls back gracefully when Redis is unavailable so
development / testing environments without a Redis server still work.
"""

from __future__ import annotations

import logging
import os
import threading

from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

log = logging.getLogger(__name__)

_redis_client: Redis | None = None
_fallback_mode: bool = False
_init_lock = threading.Lock()


def get_redis() -> Redis | None:
    """Return the shared Redis client, or None if Redis is unavailable.

    On first call this initialises a connection from environment variables:

        REDIS_URL        – full connection URI (default redis://localhost:6379/0)
        REDIS_SOCKET_TTL – socket timeout in seconds (default 5)

    If the initial connection fails or raises, the client enters *fallback mode*
    and returns None for the lifetime of the process.  Callers should always
    guard ``if get_redis() is not None:`` — never assume the connection is live.

    Thread-safe: uses double-checked locking for initialization.
    """
    global _redis_client, _fallback_mode  # noqa: PLW0603

    # Capture local reference before any check (TOCTOU-safe)
    client = _redis_client
    if client is not None:
        return client
    if _fallback_mode:
        return None

    # Double-checked locking to prevent race condition during init
    with _init_lock:
        if _redis_client is not None:
            return _redis_client
        if _fallback_mode:
            return None

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        socket_ttl = int(os.getenv("REDIS_SOCKET_TTL", "5"))

        try:
            _redis_client = Redis.from_url(
                url,
                socket_connect_timeout=socket_ttl,
                socket_timeout=socket_ttl,
                decode_responses=True,
                retry_on_timeout=True,
            )
            _redis_client.ping()
            log.info("redis: connected to %s", url)
            return _redis_client
        except (RedisConnectionError, RedisTimeoutError, OSError) as exc:
            log.warning("redis: unavailable (%s) — running in fallback mode", exc)
            _fallback_mode = True
            _redis_client = None
            return None
