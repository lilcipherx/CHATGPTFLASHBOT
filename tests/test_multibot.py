"""Multi-bot / white-label registry (ТЗ §0): encrypted tokens, default uniqueness,
tenant attribution map, and bot_id stamped on signup."""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, BotInstance
from core.services import bots
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    bots.clear_map()
    yield


async def test_token_encrypted_and_masked():
    async with SessionFactory() as s:
        b = await bots.create_bot(s, title="Brand A", token="123456:SECRET-TOKEN")
        row = await s.get(BotInstance, b.id)
        # Stored ciphertext must not contain the raw token.
        assert "SECRET-TOKEN" not in row.token
        # active_launch_specs decrypts it back for the launcher.
        specs = await bots.active_launch_specs(s)
        assert any(sp.token == "123456:SECRET-TOKEN" for sp in specs)


async def test_single_default_enforced():
    async with SessionFactory() as s:
        a = await bots.create_bot(s, title="A", token="1:a", is_default=True)
        b = await bots.create_bot(s, title="B", token="2:b", is_default=True)
        rows = {r.id: r for r in await bots.list_bots(s)}
        assert rows[b.id].is_default is True
        assert rows[a.id].is_default is False  # promoting B cleared A


async def test_identity_map_and_attribution():
    async with SessionFactory() as s:
        b = await bots.create_bot(s, title="A", token="1:a")
        await bots.record_identity(s, b.id, tg_bot_id=999, username="brand_a_bot")
        await bots.load_bot_map(s)
    assert bots.bot_id_for(999) == b.id
    assert bots.bot_id_for(None) is None
    assert bots.bot_id_for(12345) is None  # unknown bot → no tenant

    # New user arriving through that bot is stamped with its instance id.
    async with SessionFactory() as s:
        user, created = await get_or_create_user(s, 7001, bot_id=b.id)
        assert created and user.bot_id == b.id
