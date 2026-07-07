"""Feature/gate admin endpoints — gate delete + flag `default` exposure.

Calls the endpoint coroutines directly against a seeded SQLite schema (no HTTP),
mirroring tests/test_broadcast_admin.py. Covers the two additions behind the
reworked «Функции и гейты» page:
  * GET /flags now returns each flag's catalogue default (for default-vs-current).
  * DELETE /gates/{channel} removes a gate entirely (idempotent) — distinct from
    deactivating it via upsert.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest_asyncio

from api.admin.ops import delete_gate, get_flags
from core.db import SessionFactory, engine
from core.models import AdminUser, Base, ChannelGate
from core.services import feature_flags

_REQ = SimpleNamespace(client=None)


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _admin() -> AdminUser:
    async with SessionFactory() as s:
        a = AdminUser(email="flags@example.com", password_hash="x", role="superadmin")
        s.add(a)
        await s.commit()
        await s.refresh(a)
        return a


async def test_flags_endpoint_exposes_default():
    admin = await _admin()
    async with SessionFactory() as s:
        out = await get_flags(admin=admin, session=s)
    by_key = {f["key"]: f for f in out}
    # every catalogue flag is present with its default + current state
    for key, (default, _label) in feature_flags.DEFAULTS.items():
        assert by_key[key]["default"] is default
        assert by_key[key]["enabled"] is default  # no overrides yet


async def test_delete_gate_removes_and_is_idempotent():
    admin = await _admin()
    async with SessionFactory() as s:
        s.add(ChannelGate(channel="@chan", is_active=True))
        await s.commit()

    async with SessionFactory() as s:
        res = await delete_gate("@chan", request=_REQ, admin=admin, session=s)
    assert res == {"ok": True, "deleted": True}

    async with SessionFactory() as s:
        assert await s.get(ChannelGate, "@chan") is None
        # deleting again is a no-op (deleted False), never errors
        res2 = await delete_gate("@chan", request=_REQ, admin=admin, session=s)
    assert res2 == {"ok": True, "deleted": False}
