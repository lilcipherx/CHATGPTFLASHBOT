"""Panel-admins endpoint — the enriched (no-migration) serializer.

Calls the endpoint coroutines directly against a seeded SQLite schema (no HTTP),
mirroring tests/test_features_admin.py. Covers the reworked «Администраторы» page:
GET /admins now exposes last_login / created_at / updated_at / token_version (all
already on the model) so the panel can show last-login, account age and the session
generation — while still NEVER returning the password hash or the TOTP secret.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest_asyncio

from api.admin.admins import CreateAdmin as CreateAdminBody
from api.admin.admins import create_admin, list_admins
from core.db import SessionFactory, engine
from core.models import AdminUser, Base
from core.services.admin_auth import new_totp_secret


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _seed_super() -> AdminUser:
    async with SessionFactory() as s:
        a = AdminUser(email="root@example.com", password_hash="x", role="superadmin")
        s.add(a)
        await s.commit()
        await s.refresh(a)
        return a


async def test_list_exposes_timestamps_without_secrets():
    actor = await _seed_super()
    async with SessionFactory() as s:
        s.add(
            AdminUser(
                email="ops@example.com",
                password_hash="secret-hash",
                role="admin",
                totp_secret=new_totp_secret(),
                last_login=datetime.now(UTC),
                token_version=3,
            )
        )
        await s.commit()

    async with SessionFactory() as s:
        out = await list_admins(admin=actor, session=s)

    by_email = {r["email"]: r for r in out}
    ops = by_email["ops@example.com"]
    # new fields present
    assert ops["last_login"] is not None
    assert ops["created_at"] is not None
    assert ops["updated_at"] is not None
    assert ops["token_version"] == 3
    assert ops["has_2fa"] is True
    # secrets never leak in any row
    for r in out:
        assert "password_hash" not in r
        assert "totp_secret" not in r
    # an admin who never logged in / has no 2FA reads back honestly
    root = by_email["root@example.com"]
    assert root["last_login"] is None
    assert root["has_2fa"] is False


async def test_created_admin_serializes_with_new_fields():
    actor = await _seed_super()
    async with SessionFactory() as s:
        res = await create_admin(
            CreateAdminBody(email="New@Example.com", password="pw-123456", role="support"),
            request=type("R", (), {"client": None})(),
            admin=actor,
            session=s,
        )
    # email normalised, no 2FA yet, fresh account has zero session generation
    assert res["email"] == "new@example.com"
    assert res["has_2fa"] is False
    assert res["token_version"] == 0
    assert res["last_login"] is None
    assert "password_hash" not in res
