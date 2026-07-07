"""Channel-subscription gate (Gate #1): free-tier users must be members of the
admin-configured channels (channel_gates table) before using the bot.

Membership is cached in Redis per user for an hour so we don't call the Telegram
API on every message. Admins manage the channel list in the admin panel; the gate
itself is switched on/off via the `channel_gate` feature flag.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import ChannelGate
from core.redis_client import redis_client

_OK_TTL = 60 * 60  # remember a passing check for 1h
_MEMBER_STATUSES = {"creator", "administrator", "member", "owner"}


def _cache_key(user_id: int) -> str:
    return f"gate_ok:{user_id}"


async def active_channels(session: AsyncSession) -> list[str]:
    rows = (await session.scalars(
        select(ChannelGate).where(ChannelGate.is_active.is_(True))
    )).all()
    return [g.channel for g in rows]


async def is_subscribed(bot, user_id: int, session: AsyncSession) -> bool:
    """True if the user is a member of every active gate channel (or there are
    none). Cached for an hour after a successful check."""
    channels = await active_channels(session)
    if not channels:
        return True
    if await redis_client.get(_cache_key(user_id)):
        return True
    # FIX: AUDIT-13 - fail-CLOSED: track errors; if any channel raised, do NOT pass
    any_error = False
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel, user_id)
        except Exception:  # noqa: BLE001
            any_error = True
            continue
        if getattr(member, "status", None) not in _MEMBER_STATUSES:
            return False
    if any_error:
        # Do not cache, do not pass — fail-closed on Telegram API errors
        return False
    await redis_client.set(_cache_key(user_id), "1", ex=_OK_TTL)
    return True


async def clear_cache(user_id: int) -> None:
    await redis_client.delete(_cache_key(user_id))


async def clear_all_caches() -> int:
    """FIX: F27 - drop EVERY per-user gate-ok cache key. Call this whenever an admin
    adds/activates/deletes a gate channel: without it, users who previously passed the
    OLD gate set keep their `gate_ok:{uid}` cache for up to 1h (_OK_TTL) and bypass the
    NEW channel requirement until the cache expires naturally. Returns the count of
    deleted keys (best-effort: a Redis hiccup returns 0)."""
    deleted = 0
    try:
        async for key in redis_client.scan_iter(match="gate_ok:*", count=500):
            await redis_client.delete(key)
            deleted += 1
    except Exception:  # noqa: BLE001 — cache invalidation is best-effort
        pass
    return deleted
