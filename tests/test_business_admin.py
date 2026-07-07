"""Admin business-config endpoint (api/admin/business) — ТЗ §1.

Calls the endpoint coroutines directly (FastAPI leaves them callable) against a
real SQLite DB, mirroring tests/test_refunds_admin.
"""
from __future__ import annotations

import types

import pytest_asyncio
from sqlalchemy import func, select

from api.admin import business
from core.db import SessionFactory, engine
from core.models import AdminAuditLog, AdminUser, Base
from core.services import pricing
from core.services.admin_auth import hash_password


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
    # Drop the fakeredis connection bound to this test's loop (see test_pricing_config).
    try:
        await pricing.redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


def _req():
    return types.SimpleNamespace(client=None)


async def _admin(session, role="superadmin") -> AdminUser:
    a = AdminUser(email="b@x.io", password_hash=hash_password("x"), role=role, is_active=True)
    session.add(a)
    await session.commit()
    return a


async def test_get_returns_config_and_defaults():
    async with SessionFactory() as s:
        a = await _admin(s, "admin")
        out = await business.get_business_config(admin=a, session=s)
        assert "config" in out and "defaults" in out
        assert out["config"]["limits"]["free_text_weekly"] == \
            out["defaults"]["limits"]["free_text_weekly"]


async def test_put_applies_live_and_audits():
    async with SessionFactory() as s:
        a = await _admin(s, "superadmin")
        out = await business.set_business_config(
            business.ConfigPatch(patch={"avatar_price": 250, "limits": {"premium_daily": 150}}),
            _req(), admin=a, session=s,
        )
        assert out["ok"] is True
        assert out["config"]["avatar_price"] == 250
        assert out["config"]["limits"]["premium_daily"] == 150

    async with SessionFactory() as s:
        assert await pricing.avatar_price(s) == 250
        n = await s.scalar(
            select(func.count()).select_from(AdminAuditLog)
            .where(AdminAuditLog.action == "business_config.update")
        )
        assert n == 1
