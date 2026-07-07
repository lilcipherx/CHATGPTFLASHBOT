"""Maintenance mode (ТЗ §8): live-config flag + middleware that blocks non-admins."""
from __future__ import annotations

import pytest_asyncio

from bot.middlewares import maintenance as mw_mod
from bot.middlewares.maintenance import MaintenanceMiddleware
from core.db import SessionFactory, engine
from core.models import Base, User
from core.services import pricing


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield


class _Event:  # not a Message/CallbackQuery, so the middleware won't try to .answer
    pass


async def _run(session, user, *, enabled, is_admin=False, monkeypatch=None):
    if enabled:
        await pricing.set_config(session, {"maintenance": {"enabled": True, "message": "stop"}})
    calls = {"handled": False}

    async def handler(event, data):
        calls["handled"] = True
        return "ok"

    if is_admin:
        mw_mod_isadmin = mw_mod.is_admin
        mw_mod.is_admin = lambda uid: True  # noqa: ARG005
    try:
        out = await MaintenanceMiddleware()(handler, _Event(), {"user": user, "session": session})
    finally:
        if is_admin:
            mw_mod.is_admin = mw_mod_isadmin
    return calls["handled"], out


async def test_config_defaults_and_override():
    async with SessionFactory() as s:
        assert await pricing.maintenance(s) == {
            "enabled": False, "message": "🛠 Ведутся технические работы, скоро вернёмся."}
    async with SessionFactory() as s:
        await pricing.set_config(s, {"maintenance": {"enabled": True, "message": "брб"}})
    async with SessionFactory() as s:
        m = await pricing.maintenance(s)
        assert m["enabled"] is True and m["message"] == "брб"


async def test_disabled_lets_through():
    async with SessionFactory() as s:
        u = User(user_id=1, username="u", language_code="ru")
        s.add(u)
        await s.commit()
        handled, out = await _run(s, u, enabled=False)
        assert handled is True and out == "ok"


async def test_enabled_blocks_non_admin():
    async with SessionFactory() as s:
        u = User(user_id=2, username="u", language_code="ru")
        s.add(u)
        await s.commit()
        handled, out = await _run(s, u, enabled=True)
        assert handled is False and out is None


async def test_admin_bypasses_maintenance():
    async with SessionFactory() as s:
        u = User(user_id=3, username="u", language_code="ru")
        s.add(u)
        await s.commit()
        handled, _out = await _run(s, u, enabled=True, is_admin=True)
        assert handled is True
