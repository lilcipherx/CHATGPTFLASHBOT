"""Admin CRM endpoints (api/admin/crm) — ТЗ §9.

Calls the endpoint coroutines directly against a real SQLite DB, mirroring
tests/test_business_admin.
"""
from __future__ import annotations

import types

import pytest
import pytest_asyncio
from fastapi import HTTPException

from api.admin import crm
from core.db import SessionFactory, engine
from core.models import AdminUser, Base
from core.models.crm import UserNote, UserTag  # noqa: F401 — register tables
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Each pytest-asyncio test gets a fresh event loop; dispose the engine so its
    # pooled SQLite connections (which cache schema) don't leak into the next loop.
    await engine.dispose()


def _req():
    return types.SimpleNamespace(client=None)


async def _admin(session, role="admin") -> AdminUser:
    a = AdminUser(email=f"{role}@x.io", password_hash=hash_password("x"), role=role, is_active=True)
    session.add(a)
    await session.commit()
    return a


async def test_add_note_then_get_returns_it():
    async with SessionFactory() as s:
        a = await _admin(s, "support")
        out = await crm.add_note(7, crm.NoteCreate(text="  hello  "), _req(), admin=a, session=s)
        assert out["text"] == "hello"
        got = await crm.get_user_crm(7, admin=a, session=s)
        assert [n["text"] for n in got["notes"]] == ["hello"]


async def test_delete_note_removes_it():
    async with SessionFactory() as s:
        sup = await _admin(s, "support")
        adm = await _admin(s, "admin")
        note = await crm.add_note(7, crm.NoteCreate(text="x"), _req(), admin=sup, session=s)
        await crm.delete_note(note["id"], _req(), admin=adm, session=s)
        got = await crm.get_user_crm(7, admin=sup, session=s)
        assert got["notes"] == []


async def test_add_tag_twice_is_idempotent():
    async with SessionFactory() as s:
        a = await _admin(s, "support")
        await crm.add_tag(7, crm.TagCreate(tag="vip"), _req(), admin=a, session=s)
        await crm.add_tag(7, crm.TagCreate(tag="vip"), _req(), admin=a, session=s)
        got = await crm.get_user_crm(7, admin=a, session=s)
        assert got["tags"] == ["vip"]


async def test_delete_tag_removes_it():
    async with SessionFactory() as s:
        a = await _admin(s, "support")
        await crm.add_tag(7, crm.TagCreate(tag="vip"), _req(), admin=a, session=s)
        await crm.delete_tag(7, "vip", _req(), admin=a, session=s)
        got = await crm.get_user_crm(7, admin=a, session=s)
        assert got["tags"] == []


async def test_delete_missing_tag_404():
    async with SessionFactory() as s:
        a = await _admin(s, "support")
        with pytest.raises(HTTPException) as exc:
            await crm.delete_tag(7, "nope", _req(), admin=a, session=s)
        assert exc.value.status_code == 404
