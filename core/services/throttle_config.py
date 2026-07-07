"""Runtime-tunable anti-flood limits.

The throttle middleware runs as an OUTER middleware (before the DB session opens),
so reading the override from Postgres on every update would defeat the point. We
cache the (limit, window) pair in Redis for a few seconds; on a cache miss we read
the `pricing` KV table once via a short-lived session. Admins set the values from
the «Цены» page (keys ``throttle_limit`` / ``throttle_window``); blank/absent =
the settings defaults.
"""
from __future__ import annotations

import json

from core.config import settings
from core.redis_client import redis_client

_CACHE_KEY = "cache:throttle_config"
_CACHE_TTL = 30  # seconds


def _defaults() -> tuple[int, int]:
    return (max(1, settings.throttle_limit), max(1, settings.throttle_window))


async def _read_db() -> tuple[int, int]:
    from core.db import SessionFactory
    from core.models import Pricing

    limit, window = _defaults()
    try:
        async with SessionFactory() as session:
            for key, default, setter in (
                ("throttle_limit", limit, "limit"),
                ("throttle_window", window, "window"),
            ):
                row = await session.get(Pricing, key)
                if row is not None and row.value is not None:
                    try:
                        val = int(row.value if not isinstance(row.value, dict)
                                  else row.value.get("value", default))
                        if val > 0:
                            if setter == "limit":
                                limit = val
                            else:
                                window = val
                    except (TypeError, ValueError) as exc:
                        import structlog
                        structlog.get_logger().warning('core.services.throttle_config._read_db_failed', error=str(exc))
                        # FIX: AUDIT12-L1 - was silent except: pass
    except Exception:  # noqa: BLE001 — never let a config read break throttling
        return _defaults()
    return limit, window


async def get_limits() -> tuple[int, int]:
    """Return (limit, window) — Redis-cached, falling back to DB then settings."""
    try:
        raw = await redis_client.get(_CACHE_KEY)
        if raw:
            data = json.loads(raw)
            return int(data["limit"]), int(data["window"])
    except Exception:  # noqa: BLE001
        pass
    limit, window = await _read_db()
    try:
        await redis_client.set(
            _CACHE_KEY, json.dumps({"limit": limit, "window": window}), ex=_CACHE_TTL
        )
    except Exception:  # noqa: BLE001
        pass
    return limit, window
