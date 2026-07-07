"""Shared Redis connection (context store, rate-limits, FSM, cache).

REDIS_URL=memory://  -> in-process fakeredis (zero-infra dev / tests / CI).
"""
from __future__ import annotations

from core.config import settings

if settings.redis_url.startswith("memory"):
    import fakeredis.aioredis

    redis_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
else:
    import redis.asyncio as redis

    redis_client = redis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )


async def first_seen(key: str, ttl: int) -> bool:
    """Atomic best-effort dedup. Returns True the FIRST time ``key`` is seen within a
    ``ttl``-second window (and claims it), False on repeat calls. Fail-OPEN (True) when
    Redis is unavailable: a tracking blip should over-count, never block the request
    path. Used to collapse repeat impressions/clicks/redirects from the same
    viewer so the counters approximate unique reach instead of raw fire count."""
    try:
        return bool(await redis_client.set(key, "1", ex=ttl, nx=True))
    except Exception as exc:  # noqa: BLE001 — FIX: F35 - log so a Redis outage
        # surfacing as silent over-counting is observable (was bare `return True`).
        # Fail-open behaviour is unchanged: tracking dedup is best-effort.
        import structlog
        structlog.get_logger().warning("redis.first_seen_failed", key=key, error=str(exc))
        return True
