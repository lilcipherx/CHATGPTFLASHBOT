"""Preset roles / personas (ТЗ §3): admin-editable persona list + /roles picker."""
from __future__ import annotations

import pytest_asyncio

from bot.handlers.roles import _roles_keyboard
from core.db import SessionFactory, engine
from core.i18n import Translator
from core.models import Base
from core.services import pricing

_T = Translator("ru")


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


async def test_default_roles_present():
    async with SessionFactory() as s:
        roles = await pricing.preset_roles(s)
        keys = {r["key"] for r in roles}
        assert {"tutor", "coder"} <= keys
        assert all(r["prompt"] for r in roles)


async def test_resolve_role_by_key():
    async with SessionFactory() as s:
        r = await pricing.preset_role(s, "coder")
        assert r is not None and "разработчик" in r["prompt"].lower()
        assert await pricing.preset_role(s, "____nope____") is None


async def test_admin_override_and_malformed_filtered():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"preset_roles": [
            {"key": "lawyer", "title": "Юрист", "prompt": "Ты юрист."},
            {"title": "broken — no key/prompt"},   # dropped
            {"key": "noprompt", "title": "x"},      # dropped (no prompt)
        ]})
    async with SessionFactory() as s:
        roles = await pricing.preset_roles(s)
        assert [r["key"] for r in roles] == ["lawyer"]


async def test_keyboard_builds_and_empty():
    async with SessionFactory() as s:
        kb = await _roles_keyboard(s, _T)
        # default roles + a trailing "off" row
        assert kb is not None and len(kb.inline_keyboard) >= 2
        assert kb.inline_keyboard[-1][0].callback_data == "role:off"
    async with SessionFactory() as s:
        await pricing.set_config(s, {"preset_roles": []})
    async with SessionFactory() as s:
        assert await _roles_keyboard(s, _T) is None
