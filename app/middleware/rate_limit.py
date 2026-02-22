from __future__ import annotations

import time

from fastapi import HTTPException, Request
from redis.asyncio import Redis

from app.config import settings


def _key(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    path = request.url.path
    return f"rl:{ip}:{path}"


async def rate_limit(request: Request) -> None:
    # Very small, dependency-based rate limiter.
    # Use depends(rate_limit) on routes.
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


def utc_now_ts() -> int:
    return int(time.time())
