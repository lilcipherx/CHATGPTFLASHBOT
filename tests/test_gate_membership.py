"""Channel-subscription gate membership loop (Loop coverage): the fail-CLOSED
behaviour when the Telegram API errors, the member/non-member decisions, and the 1h
Redis cache. Complements test_features.py (which only covers the no-channels pass).
Uses fakeredis (memory://) + a stub bot; no network.
"""
from __future__ import annotations

import types

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, ChannelGate
from core.services import gate


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


class _Bot:
    """Stub aiogram bot: maps channel -> status string, or raises for a channel."""
    def __init__(self, status="member", raise_on=None):
        self._status = status
        self._raise_on = raise_on or set()

    async def get_chat_member(self, channel, user_id):
        if channel in self._raise_on:
            raise RuntimeError("telegram api down")
        return types.SimpleNamespace(status=self._status)


async def _add_channels():
    async with SessionFactory() as s:
        s.add(ChannelGate(channel="@a", is_active=True))
        s.add(ChannelGate(channel="@b", is_active=True))
        await s.commit()


async def test_member_of_all_channels_passes_and_caches():
    await _add_channels()
    async with SessionFactory() as s:
        assert await gate.is_subscribed(bot=_Bot("member"), user_id=100, session=s) is True
        # Second call is served from the Redis cache — bot=None must still pass.
        assert await gate.is_subscribed(bot=None, user_id=100, session=s) is True


async def test_non_member_is_rejected():
    await _add_channels()
    async with SessionFactory() as s:
        assert await gate.is_subscribed(bot=_Bot("left"), user_id=101, session=s) is False


async def test_fail_closed_on_telegram_error():
    await _add_channels()
    async with SessionFactory() as s:
        # A channel that raises → any_error → do NOT pass and do NOT cache.
        bot = _Bot("member", raise_on={"@b"})
        assert await gate.is_subscribed(bot=bot, user_id=102, session=s) is False
        # Not cached: a subsequent good check must be able to pass.
        assert await gate.is_subscribed(bot=_Bot("member"), user_id=102, session=s) is True


async def test_clear_cache_and_clear_all():
    await _add_channels()
    async with SessionFactory() as s:
        assert await gate.is_subscribed(bot=_Bot("member"), user_id=103, session=s) is True
        await gate.clear_cache(103)
        # After clearing, a bot=None call has no cache → must re-check (non-member now).
        assert await gate.is_subscribed(bot=_Bot("left"), user_id=103, session=s) is False

    async with SessionFactory() as s:
        await gate.is_subscribed(bot=_Bot("member"), user_id=104, session=s)
        deleted = await gate.clear_all_caches()
        assert deleted >= 1
