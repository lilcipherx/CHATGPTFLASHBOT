"""Admin management endpoints (api/admin/admins) — ТЗ §8.

Direct endpoint-coroutine calls against a real SQLite DB (pattern:
tests/test_business_admin), seeding superadmins via the `_admin` helper.
"""
from __future__ import annotations

import types

import pytest
import pytest_asyncio

from api.admin import admins
from core.db import SessionFactory, engine
from core.models import AdminUser, Base
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req():
    return types.SimpleNamespace(client=None)


async def _admin(session, email="root@x.io", role="superadmin", active=True) -> AdminUser:
    a = AdminUser(
        email=email, password_hash=hash_password("x"), role=role, is_active=active
    )
    session.add(a)
    await session.commit()
    return a


async def test_list_admins():
    async with SessionFactory() as s:
        a = await _admin(s)
        await _admin(s, email="support@x.io", role="support")
        out = await admins.list_admins(admin=a, session=s)
        assert len(out) == 2
        emails = {r["email"] for r in out}
        assert emails == {"root@x.io", "support@x.io"}
        # Never leak secrets.
        assert all("password_hash" not in r and "totp_secret" not in r for r in out)
        assert all(
            set(r) == {
                "id", "email", "role", "is_active", "has_2fa",
                "last_login", "created_at", "updated_at", "token_version",
            }
            for r in out
        )


async def test_create_admin_and_duplicate():
    async with SessionFactory() as s:
        a = await _admin(s)
        out = await admins.create_admin(
            admins.CreateAdmin(email="New@X.io", password="password123", role="admin"),
            _req(), admin=a, session=s,
        )
        assert out["email"] == "new@x.io"  # normalized lower
        assert out["role"] == "admin"
        assert out["is_active"] is True
        # Duplicate email (case-insensitive) → 400.
        with pytest.raises(Exception):  # noqa: B017,PT011 - HTTPException 400
            await admins.create_admin(
                admins.CreateAdmin(email="NEW@x.io", password="password123", role="admin"),
                _req(), admin=a, session=s,
            )


async def test_create_admin_invalid_role():
    async with SessionFactory() as s:
        a = await _admin(s)
        with pytest.raises(Exception):  # noqa: B017
            await admins.create_admin(
                admins.CreateAdmin(email="x@x.io", password="password123", role="god"),
                _req(), admin=a, session=s,
            )


async def test_change_role():
    async with SessionFactory() as s:
        a = await _admin(s)
        target = await _admin(s, email="t@x.io", role="support")
        out = await admins.set_admin_role(
            target.id, admins.RoleChange(role="moderator"), _req(), admin=a, session=s
        )
        assert out["role"] == "moderator"


async def test_cannot_demote_last_superadmin():
    async with SessionFactory() as s:
        a = await _admin(s)  # only superadmin
        with pytest.raises(Exception):  # noqa: B017 - HTTPException 400
            await admins.set_admin_role(
                a.id, admins.RoleChange(role="admin"), _req(), admin=a, session=s
            )
        # still superadmin
        again = await admins.list_admins(admin=a, session=s)
        assert again[0]["role"] == "superadmin"


async def test_can_demote_when_another_superadmin_exists():
    async with SessionFactory() as s:
        a = await _admin(s)
        b = await _admin(s, email="b@x.io", role="superadmin")
        out = await admins.set_admin_role(
            b.id, admins.RoleChange(role="admin"), _req(), admin=a, session=s
        )
        assert out["role"] == "admin"


async def test_cannot_disable_last_superadmin():
    async with SessionFactory() as s:
        a = await _admin(s)
        with pytest.raises(Exception):  # noqa: B017
            await admins.disable_admin(a.id, _req(), admin=a, session=s)


async def test_disable_bumps_token_version():
    async with SessionFactory() as s:
        a = await _admin(s)
        target = await _admin(s, email="t@x.io", role="admin")
        before = target.token_version
        out = await admins.disable_admin(target.id, _req(), admin=a, session=s)
        assert out["is_active"] is False

    async with SessionFactory() as s:
        refreshed = await s.get(AdminUser, target.id)
        assert refreshed.token_version == before + 1
        assert refreshed.is_active is False


async def test_enable_admin():
    async with SessionFactory() as s:
        a = await _admin(s)
        target = await _admin(s, email="t@x.io", role="admin", active=False)
        out = await admins.enable_admin(target.id, _req(), admin=a, session=s)
        assert out["is_active"] is True


async def test_logout_all_bumps_token_version():
    """Ending all sessions revokes every JWT by bumping token_version."""
    async with SessionFactory() as s:
        root = await _admin(s)
        target = await _admin(s, email="t@x.io", role="admin")
        before = target.token_version
        out = await admins.logout_all_admin(target.id, _req(), admin=root, session=s)
        assert out["token_version"] == before + 1
    async with SessionFactory() as s:
        t = await s.get(AdminUser, target.id)
        assert t.token_version == before + 1


async def test_admin_sessions_group_by_device_and_ip():
    """Active sessions are derived from successful-login audit rows, grouped by
    device (user-agent) + IP, newest first."""
    from datetime import UTC, datetime, timedelta

    from core.models import AdminAuditLog

    async with SessionFactory() as s:
        root = await _admin(s)
        target = await _admin(s, email="u@x.io", role="admin")
        now = datetime.now(UTC)
        s.add_all([
            AdminAuditLog(admin_id=target.id, action="auth.login", ip="1.1.1.1",
                          after={"device": "Mozilla/5.0 (Windows NT) Chrome/120"}, created_at=now),
            AdminAuditLog(admin_id=target.id, action="auth.login", ip="1.1.1.1",
                          after={"device": "Mozilla/5.0 (Windows NT) Chrome/120"},
                          created_at=now - timedelta(hours=1)),
            AdminAuditLog(admin_id=target.id, action="auth.login", ip="2.2.2.2",
                          after={"device": "Mozilla/5.0 (iPhone) Safari"},
                          created_at=now - timedelta(days=1)),
            AdminAuditLog(admin_id=target.id, action="auth.login_failed", ip="3.3.3.3",
                          after={"device": "x"}, created_at=now),  # failures excluded
        ])
        await s.commit()
        out = await admins.admin_sessions(target.id, admin=root, session=s)
    sess = out["sessions"]
    assert len(sess) == 2                       # two distinct device+ip, failures dropped
    assert sess[0]["count"] == 2                # the Windows/Chrome bucket has 2 logins
    assert "Chrome" in sess[0]["device"] and sess[0]["ip"] == "1.1.1.1"
