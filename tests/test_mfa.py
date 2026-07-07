"""Mandatory 2FA enrollment for privileged roles (ТЗ §8).

A privileged role (admin/superadmin) with the correct password but no enrolled
TOTP secret gets a restricted "mfa_setup"-scoped session that can ONLY enroll 2FA;
every full admin endpoint rejects that scope.
"""
from __future__ import annotations

import types

import pyotp
import pytest
import pytest_asyncio
from fastapi import HTTPException, Response

from api.admin import auth as auth_api
from api.admin import deps
from core.db import SessionFactory, engine
from core.models import AdminUser, Base
from core.services import admin_auth
from core.services.admin_auth import hash_password


def _req(ip: str = "127.0.0.1"):
    """Minimal stand-in for the FastAPI Request the login endpoint audits the IP +
    user-agent (device) from. A real Starlette Request always has `.headers`."""
    return types.SimpleNamespace(client=types.SimpleNamespace(host=ip), headers={})


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _seed(session, *, role, email="root@x.io", secret=None):
    a = AdminUser(
        email=email, password_hash=hash_password("pw"), role=role,
        is_active=True, totp_secret=secret,
    )
    session.add(a)
    await session.commit()
    return a


def test_mfa_required_roles():
    assert admin_auth.mfa_required("admin") is True
    assert admin_auth.mfa_required("superadmin") is True
    assert admin_auth.mfa_required("support") is False
    assert admin_auth.mfa_required("moderator") is False


async def test_privileged_login_without_2fa_gets_setup_scope():
    async with SessionFactory() as s:
        await _seed(s, role="admin")
        out = await auth_api.login(
            auth_api.LoginRequest(email="root@x.io", password="pw"),
            Response(), request=_req(), _=None, session=s,
        )
        assert out.mfa_setup_required is True
        assert out.refresh_token == ""  # no full session granted
        payload = admin_auth.decode_token(out.access_token)
        assert payload["scope"] == "mfa_setup"


async def test_support_login_no_2fa_is_full():
    async with SessionFactory() as s:
        await _seed(s, role="support", email="sup@x.io")
        out = await auth_api.login(
            auth_api.LoginRequest(email="sup@x.io", password="pw"),
            Response(), request=_req(), _=None, session=s,
        )
        assert out.mfa_setup_required is False
        assert out.refresh_token != ""
        assert admin_auth.decode_token(out.access_token)["scope"] == "full"


async def test_setup_scope_rejected_by_full_endpoints():
    async with SessionFactory() as s:
        a = await _seed(s, role="admin")
        setup_tok = admin_auth.create_token(
            a.id, a.role, ver=a.token_version, scope="mfa_setup"
        )
        # current_admin (full) must reject the restricted scope...
        with pytest.raises(HTTPException) as exc:
            await deps.current_admin(
                _=None, authorization=f"Bearer {setup_tok}", admin_access="", session=s
            )
        assert exc.value.status_code == 403
        # ...but the enrolling dependency accepts it.
        admin = await deps.current_admin_enrolling(
            _=None, authorization=f"Bearer {setup_tok}", admin_access="", session=s
        )
        assert admin.id == a.id


async def test_enable_2fa_bumps_version_and_requires_relogin():
    async with SessionFactory() as s:
        a = await _seed(s, role="admin")
        before = a.token_version
        secret = admin_auth.new_totp_secret()
        code = pyotp.TOTP(secret).now()
        out = await auth_api.twofa_enable(
            auth_api.TwoFAEnable(secret=secret, code=code),
            Response(), _req(), admin=a, session=s,
        )
        assert out["enabled"] is True
        assert out["relogin_required"] is True
        refreshed = await s.get(AdminUser, a.id)
        # FIX: AUDIT-TEST - TOTP secrets are stored ENCRYPTED at rest (enc:: prefix);
        # decrypt before comparing to the plaintext secret.
        from core.services.crypto import decrypt
        assert decrypt(refreshed.totp_secret) == secret
        assert refreshed.token_version == before + 1


async def test_full_login_after_enrollment_requires_otp():
    async with SessionFactory() as s:
        secret = admin_auth.new_totp_secret()
        await _seed(s, role="admin", secret=secret)
        # No OTP → 401 otp_required.
        with pytest.raises(HTTPException) as exc:
            await auth_api.login(
                auth_api.LoginRequest(email="root@x.io", password="pw"),
                Response(), request=_req(), _=None, session=s,
            )
        assert exc.value.detail == "otp_required"
        # Correct OTP → full session.
        out = await auth_api.login(
            auth_api.LoginRequest(
                email="root@x.io", password="pw", otp=pyotp.TOTP(secret).now()
            ),
            Response(), request=_req(), _=None, session=s,
        )
        assert out.mfa_setup_required is False
        assert admin_auth.decode_token(out.access_token)["scope"] == "full"
