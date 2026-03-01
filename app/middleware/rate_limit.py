from __future__ import annotations

import logging
import time

from fastapi import HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

# In-memory fallback when Redis is unavailable
# Maps key -> (count, window_start_timestamp)
_memory_store: dict[str, tuple[int, float]] = {}
_redis_warned = False
_cleanup_counter = 0


def _key(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    path = request.url.path
    return f"rl:{ip}:{path}"


def _memory_cleanup() -> None:
    """Remove expired entries from in-memory store."""
    global _cleanup_counter
    _cleanup_counter += 1
    if _cleanup_counter < 100:
        return
    _cleanup_counter = 0
    now = time.time()
    window = settings.RATE_LIMIT_WINDOW_SECONDS
    expired = [k for k, (_, ts) in _memory_store.items() if now - ts > window]
    for k in expired:
        del _memory_store[k]


def _memory_rate_limit(request: Request) -> None:
    """In-memory rate limiter fallback."""
    key = _key(request)
    now = time.time()
    window = settings.RATE_LIMIT_WINDOW_SECONDS

    entry = _memory_store.get(key)
    if entry is None or (now - entry[1]) > window:
        _memory_store[key] = (1, now)
        _memory_cleanup()
        return

    count = entry[0] + 1
    _memory_store[key] = (count, entry[1])

    if count > settings.RATE_LIMIT_REQUESTS:
        retry_after = max(0, int(window - (now - entry[1])))
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "retry_after_seconds": retry_after},
        )
    _memory_cleanup()


async def rate_limit(request: Request) -> None:
    """Dependency-based rate limiter. Falls back to in-memory if Redis is unavailable."""
    global _redis_warned
    try:
        from redis.asyncio import Redis

        redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        key = _key(request)

        try:
            cur = await redis.incr(key)
            if cur == 1:
                await redis.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS)

            if cur > settings.RATE_LIMIT_REQUESTS:
                ttl = await redis.ttl(key)
                raise HTTPException(
                    status_code=429,
                    detail={"error": "rate_limited", "retry_after_seconds": max(ttl, 0)},
                )
        finally:
            await redis.aclose()
        _redis_warned = False
    except HTTPException:
        raise
    except Exception:
        if not _redis_warned:
            logger.warning("Redis unavailable — using in-memory rate limiting")
            _redis_warned = True
        _memory_rate_limit(request)
