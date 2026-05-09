"""Caching helpers and distributed lock utilities built on top of app.core.cache.

app.core.cache owns the Redis client singleton.  This module adds:
  - cache_get / cache_set with Prometheus hit/miss tracking
  - acquire_lock / release_lock for scheduler dedup

Import `get_redis` from app.core.cache for raw client access.
"""

from __future__ import annotations

from typing import Optional

from app.core.cache import get_redis
from app.core.logging import get_logger
from app.core.metrics import cache_hits, cache_misses

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_redis_dep():  # type: ignore[return]
    """FastAPI dependency — returns the shared Redis client from app.core.cache."""
    return await get_redis()


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _key_prefix(key: str) -> str:
    """Extract the colon-delimited prefix for metric labelling."""
    return key.split(":")[0] if ":" in key else key


async def cache_get(key: str) -> Optional[str]:
    """Return cached value or None, recording hit/miss metrics."""
    client = await get_redis()
    try:
        value: str | None = await client.get(key)
    except Exception:
        log.warning("redis_get_error", key=key)
        return None

    prefix = _key_prefix(key)
    if value is not None:
        cache_hits.labels(key_prefix=prefix).inc()
    else:
        cache_misses.labels(key_prefix=prefix).inc()
    return value


async def cache_set(key: str, value: str, ttl_seconds: int = 300) -> None:
    """Set *key* → *value* with an expiry."""
    client = await get_redis()
    try:
        await client.setex(key, ttl_seconds, value)
    except Exception:
        log.warning("redis_set_error", key=key)


async def acquire_lock(key: str, ttl_seconds: int = 30) -> bool:
    """Attempt to acquire a distributed lock via SET NX EX.

    Returns True if the lock was acquired, False if it's already held.
    Used by the scheduler to prevent duplicate reminder firings across
    multiple Dyno/container instances running the same APScheduler job.

    SET NX EX is a single atomic command — no WATCH/MULTI needed.
    """
    lock_key = f"lock:{key}"
    client = await get_redis()
    try:
        result = await client.set(lock_key, "1", nx=True, ex=ttl_seconds)
        return result is True
    except Exception:
        log.error("redis_lock_error", lock_key=lock_key)
        # Fail open: if Redis is down, let the job run rather than deadlock
        return True


async def release_lock(key: str) -> None:
    """Release a previously acquired lock."""
    lock_key = f"lock:{key}"
    client = await get_redis()
    try:
        await client.delete(lock_key)
    except Exception:
        log.warning("redis_lock_release_error", lock_key=lock_key)
