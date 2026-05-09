"""
Redis-backed sliding-window rate limiter for per-NGO webhook endpoints.

Why sorted sets (ZSET) over a simple INCR counter:
  - A fixed counter resets at hard bucket boundaries (e.g. :00 every minute).
    An attacker can send 30 req at :59 and 30 more at :01 — 60 req in 2 s,
    none rejected.
  - A sorted set keyed by timestamp gives a true sliding window: we always
    count only the requests in the last `window_seconds` seconds, regardless
    of when the clock ticks.

Redis commands used (all atomic via pipeline):
  ZREMRANGEBYSCORE  remove members older than the window
  ZADD              record this request with score = current epoch ms
  ZCARD             count requests inside the window
  EXPIRE            auto-clean the key after the window (avoids memory leak)
"""

from __future__ import annotations

import time
from typing import Optional

from app.core.cache import get_redis
from app.core.logging import get_logger

logger = get_logger(__name__)


async def check_rate_limit(
    key: str,           # e.g. "ratelimit:webhook:helpngo"
    max_requests: int,  # e.g. 30
    window_seconds: int, # e.g. 60
) -> tuple[bool, int]:
    """Sliding-window rate limiter using a Redis sorted set.

    Returns (allowed: bool, remaining: int).

    If Redis is unavailable the function fails open (returns allowed=True,
    remaining=max_requests) and logs a warning so we never block legitimate
    traffic due to a cache outage.
    """
    now_ms = int(time.time() * 1000)
    window_start_ms = now_ms - (window_seconds * 1000)

    try:
        redis = await get_redis()
        pipe = redis.pipeline()
        # Remove timestamps older than the sliding window
        pipe.zremrangebyscore(key, "-inf", window_start_ms)
        # Record this request; score = current ms, member = unique ms value
        # Using str(now_ms) as member risks collision at identical ms — use a
        # unique suffix to prevent members overwriting each other on high-volume
        member = f"{now_ms}-{id(pipe)}"
        pipe.zadd(key, {member: now_ms})
        # Count how many requests are in the window
        pipe.zcard(key)
        # Set TTL so the key expires if traffic stops
        pipe.expire(key, window_seconds + 1)
        results = await pipe.execute()

        count: int = results[2]  # result of ZCARD
        allowed = count <= max_requests
        remaining = max(0, max_requests - count)
        return allowed, remaining

    except Exception as exc:
        logger.warning(
            "rate_limiter_redis_error",
            key=key,
            error=str(exc),
        )
        # Fail open — never block traffic due to a Redis outage
        return True, max_requests


async def is_webhook_allowed(ngo_slug: str) -> tuple[bool, int]:
    """30 requests/minute per NGO — Telegram normally sends 1 update at a time.

    Returns (allowed: bool, remaining: int).
    Use the `allowed` flag to decide whether to process the update or discard.
    """
    return await check_rate_limit(
        f"ratelimit:webhook:{ngo_slug}",
        max_requests=30,
        window_seconds=60,
    )
