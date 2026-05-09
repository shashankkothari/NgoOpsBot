"""
Redis client singleton for the application.

We use a lazy-initialised module-level client rather than a FastAPI
lifespan dependency so the cache is accessible from background tasks
(scheduler jobs, webhook background tasks) that don't have request context.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import get_settings

_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the shared Redis client, creating it on first call."""
    global _redis_client  # noqa: PLW0603
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            # Single shared pool is fine; asyncio serialises coroutine execution
            max_connections=20,
        )
    return _redis_client


async def close_redis() -> None:
    """Close the Redis connection pool — call from app shutdown lifespan."""
    global _redis_client  # noqa: PLW0603
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


async def ping_redis() -> bool:
    """Return True if Redis is reachable. Used by the readiness probe."""
    try:
        client = await get_redis()
        return await client.ping()
    except Exception:
        return False
