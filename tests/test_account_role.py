"""Active role visibility in /account + «custom role» entry from /roles (ТЗ §3)."""
from __future__ import annotations

import pytest_asyncio

from bot.handlers.account import _role_line
from bot.handlers.roles import _roles_keyboard
from core.db import SessionFactory, engine
from core.i18n import Translator
from core.models import Base
from core.services import pricing
from core.services.users import get_or_create_user, set_role

_ROLES = [{"key": "tutor", "title": "👩‍🏫 Репетитор", "prompt": "Ты репетитор."}]


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
    try:
        await pricing.redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


async def test_role_line_empty_when_no_role():
    _ = Translator("ru")
    async with SessionFactory() as s:
        user, _c = await get_or_create_user(s, 1)
        assert await _role_line(s, user, _) == ""


async def test_role_line_names_preset_by_prompt():
    _ = Translator("ru")
    async with SessionFactory() as s:
        await pricing.set_config(s, {"preset_roles": _ROLES})
    async with SessionFactory() as s:
        user, _c = await get_or_create_user(s, 2)
        await set_role(s, user, "Ты репетитор.")   # matches the tutor preset prompt
        line = await _role_line(s, user, _)
        assert "🎭" in line and "Репетитор" in line


async def test_role_line_custom_when_no_preset_match():
    _ = Translator("ru")
    async with SessionFactory() as s:
        await pricing.set_config(s, {"preset_roles": _ROLES})
    async with SessionFactory() as s:
        user, _c = await get_or_create_user(s, 3)
        await set_role(s, user, "Совершенно своя инструкция")  # matches no preset
        line = await _role_line(s, user, _)
        assert "🎭" in line and "своя роль" in line


async def test_preset_roles_expose_desc():
    async with SessionFactory() as s:
        # default config ships descriptions on the built-in personas
        roles = await pricing.preset_roles(s)
        assert roles and all("desc" in r for r in roles)
        assert any(r["desc"] for r in roles)
    async with SessionFactory() as s:
        await pricing.set_config(s, {"preset_roles": [
            {"key": "k", "title": "T", "prompt": "P", "desc": "one-liner"}]})
    async with SessionFactory() as s:
        roles = await pricing.preset_roles(s)
        assert roles[0]["desc"] == "one-liner"


async def test_roles_keyboard_has_custom_button():
    _ = Translator("ru")
    async with SessionFactory() as s:
        await pricing.set_config(s, {"preset_roles": _ROLES})
    async with SessionFactory() as s:
        kb = await _roles_keyboard(s, _)
        cbs = [b.callback_data for row in kb.inline_keyboard for b in row]
        assert "role:custom" in cbs and "role:off" in cbs
