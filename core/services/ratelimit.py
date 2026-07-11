"""Redis fixed-window rate limiter for antifraud / throttling (§13 Phase 7)."""
from __future__ import annotations

from core.redis_client import redis_client


async def allow(key: str, limit: int, window_seconds: int) -> bool:
    """Increment a fixed-window counter; return False once it exceeds `limit`.

    INCR + EXPIRE run in a single pipeline so a crash between them can't leave the
    counter without a TTL (which would block the key forever). NX keeps the TTL
    anchored to the first hit of the window instead of sliding it on every call.
    """
    full_key = f"rl:{key}"
    pipe = redis_client.pipeline()
    pipe.incr(full_key)
    pipe.expire(full_key, window_seconds, nx=True)
    try:
        count, _ = await pipe.execute()
        return count <= limit
    except Exception:  # noqa: BLE001 — FIX: N4 - Redis down: fail-open so the bot stays reachable (throttle is best-effort; argon2+RBAC are the real gates)
        return True


async def peek(key: str) -> int:
    """Current counter value without incrementing (0 if unset). Fail-open (0) on a
    Redis error so a gate built on this never locks a caller out on an outage."""
    try:
        v = await redis_client.get(f"rl:{key}")
        return int(v) if v else 0
    except Exception:  # noqa: BLE001 — Redis down: report 0 so gates fail open
        return 0


async def incr(key: str, window_seconds: int) -> int:
    """Increment a counter with an anchored TTL and return the new value (0 on a Redis
    error). Use for failure counters that must reset only via :func:`reset`."""
    full_key = f"rl:{key}"
    pipe = redis_client.pipeline()
    pipe.incr(full_key)
    pipe.expire(full_key, window_seconds, nx=True)
    try:
        count, _ = await pipe.execute()
        return int(count)
    except Exception:  # noqa: BLE001 — Redis down: fail open
        return 0


async def reset(key: str) -> None:
    """Clear a counter (e.g. a per-account failure counter after a successful login)."""
    try:
        await redis_client.delete(f"rl:{key}")
    except Exception:  # noqa: BLE001 — best-effort
        pass
