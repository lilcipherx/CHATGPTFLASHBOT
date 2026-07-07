"""Admin authentication is now audited (§8 security): every login attempt — success
or failure — and every logout (revoke-all-sessions) writes an admin_audit_log row,
so the Security Center can surface login history, failed attempts and brute-force
signals. Calls the endpoint coroutines directly against a seeded SQLite DB.
"""
from __future__ import annotations

import types

import pyotp
import pytest
import pytest_asyncio
from fastapi import HTTPException, Response
from sqlalchemy import select

from api.admin import auth
from core.db import SessionFactory, engine
from core.models import AdminAuditLog, AdminUser, Base
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req(ip: str = "1.2.3.4"):
    # A real Starlette Request always has `.headers`; the login endpoint reads the
    # user-agent from it for device/session history.
    return types.SimpleNamespace(client=types.SimpleNamespace(host=ip), headers={})


async def _mk(*, email="root@x.io", password="secret123", role="support",
             twofa: str | None = None, active=True) -> AdminUser:
    async with SessionFactory() as s:
        a = AdminUser(email=email, password_hash=hash_password(password), role=role,
                      is_active=active, totp_secret=twofa)
        s.add(a)
        await s.commit()
        await s.refresh(a)
        return a


async def _rows(action: str | None = None) -> list[AdminAuditLog]:
    async with SessionFactory() as s:
        rows = (await s.scalars(
            select(AdminAuditLog).order_by(AdminAuditLog.id.desc()))).all()
    return [r for r in rows if action is None or r.action == action]


async def _login(**kw):
    async with SessionFactory() as s:
        return await auth.login(
            req=auth.LoginRequest(**{"email": "root@x.io", "password": "secret123", **kw}),
            response=Response(), request=_req(), _=None, session=s,
        )


# ---- timing-equalizer (account-enumeration defence) ------------------------
def test_verify_password_dummy_runs_and_swallows():
    """The login-timing equalizer must spend argon2 time without raising for any
    input, so an unknown/inactive email costs the same as a real wrong password."""
    from core.services.admin_auth import _DUMMY_HASH, verify_password_dummy

    assert _DUMMY_HASH.startswith("$argon2")  # a real argon2 hash, not a stub
    assert verify_password_dummy("anything") is None
    assert verify_password_dummy("") is None


# ---- successful login ------------------------------------------------------
async def test_successful_login_audited():
    a = await _mk()
    res = await _login()
    assert res.access_token
    rows = await _rows("auth.login")
    assert len(rows) == 1
    r = rows[0]
    assert r.admin_id == a.id
    assert r.ip == "1.2.3.4"
    # `device` (user-agent) is also recorded for login/session history — empty here
    # since the stand-in request carries no User-Agent header.
    assert r.after == {"email": "root@x.io", "reason": "ok", "success": True, "device": ""}


# ---- failures --------------------------------------------------------------
async def test_bad_password_audited():
    await _mk()
    with pytest.raises(HTTPException) as ei:
        await _login(password="wrong")
    assert ei.value.status_code == 401
    rows = await _rows("auth.login_failed")
    assert len(rows) == 1
    assert rows[0].after["reason"] == "bad_password"
    assert rows[0].after["success"] is False


async def test_unknown_email_audited_with_zero_admin():
    with pytest.raises(HTTPException):
        await _login(email="ghost@x.io", password="whatever")
    rows = await _rows("auth.login_failed")
    assert len(rows) == 1
    assert rows[0].admin_id == 0
    assert rows[0].after["reason"] == "unknown_email"
    assert rows[0].after["email"] == "ghost@x.io"


async def test_inactive_account_audited():
    a = await _mk(active=False)
    with pytest.raises(HTTPException):
        await _login()
    rows = await _rows("auth.login_failed")
    assert rows[0].admin_id == a.id
    assert rows[0].after["reason"] == "inactive"


# ---- 2FA branches ----------------------------------------------------------
async def test_otp_required_audited():
    secret = pyotp.random_base32()
    await _mk(twofa=secret)
    with pytest.raises(HTTPException) as ei:
        await _login()  # no otp provided
    assert ei.value.detail == "otp_required"
    assert (await _rows("auth.login_failed"))[0].after["reason"] == "otp_required"


async def test_otp_invalid_audited():
    secret = pyotp.random_base32()
    await _mk(twofa=secret)
    with pytest.raises(HTTPException) as ei:
        await _login(otp="000000")
    assert ei.value.detail == "otp_invalid"
    assert (await _rows("auth.login_failed"))[0].after["reason"] == "otp_invalid"


async def test_otp_valid_login_audited():
    secret = pyotp.random_base32()
    await _mk(twofa=secret)
    res = await _login(otp=pyotp.TOTP(secret).now())
    assert res.access_token
    assert (await _rows("auth.login"))[0].after["reason"] == "ok"


async def test_mfa_setup_login_audited():
    # admin role requires 2FA (default mfa_required_roles) but has none → setup scope.
    await _mk(role="admin", twofa=None)
    res = await _login()
    assert res.mfa_setup_required is True
    assert (await _rows("auth.login"))[0].after["reason"] == "mfa_setup"


# ---- logout ----------------------------------------------------------------
async def test_logout_audited_and_revokes():
    a = await _mk()
    async with SessionFactory() as s:
        fresh = await s.get(AdminUser, a.id)
        before_ver = fresh.token_version
        await auth.logout(response=Response(), request=_req("9.9.9.9"), admin=fresh, session=s)
    rows = await _rows("auth.logout")
    assert len(rows) == 1
    assert rows[0].admin_id == a.id
    assert rows[0].ip == "9.9.9.9"
    async with SessionFactory() as s:
        assert (await s.get(AdminUser, a.id)).token_version == before_ver + 1
