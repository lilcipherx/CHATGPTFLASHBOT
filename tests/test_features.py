"""Feature flags + channel-gate logic (admin-controlled behaviour)."""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, ChannelGate
from core.services import credits, feature_flags, gate
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_flag_defaults_and_override():
    async with SessionFactory() as s:
        # full-product launch: every flag defaults ON (gate is a safe no-op until a
        # channel is added; provider-backed services refund until a key is wired).
        assert await feature_flags.is_enabled(s, "channel_gate") is True
        assert await feature_flags.is_enabled(s, "faceswap") is True
        assert await feature_flags.is_enabled(s, "vision") is True
        # admin turns a flag off → override persists and reads back
        await feature_flags.set_flag(s, "faceswap", False)
        assert await feature_flags.is_enabled(s, "faceswap") is False
        # full catalogue is returned merged over defaults
        flags = await feature_flags.get_flags(s)
        assert flags["faceswap"] is False and "upscale" in flags


async def test_gate_passes_when_no_channels():
    async with SessionFactory() as s:
        # no active channels configured → everyone passes
        assert await gate.is_subscribed(bot=None, user_id=1, session=s) is True


async def test_gate_active_channels_lists_only_active():
    async with SessionFactory() as s:
        s.add(ChannelGate(channel="@a", is_active=True))
        s.add(ChannelGate(channel="@b", is_active=False))
        await s.commit()
        assert await gate.active_channels(s) == ["@a"]


async def test_credits_atomic_consume_and_refund():
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 7001)
        await credits.grant(s, user, 5)
        assert await credits.get_balance(s, 7001) == 5
        assert await credits.try_consume(s, user, 3) is True
        assert await credits.get_balance(s, 7001) == 2
        # over-spend rejected, balance unchanged
        assert await credits.try_consume(s, user, 5) is False
        assert await credits.get_balance(s, 7001) == 2
        # refund (grant) tops back up
        await credits.grant(s, user, 3)
        assert await credits.get_balance(s, 7001) == 5
