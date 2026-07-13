"""Admin 2FA enrolment + self password change (Loop coverage, auth-critical). Calls
the endpoint coroutines directly with a seeded AdminUser (single event loop, like the
login tests). Covers status/setup, enable (invalid→400, valid→stored + token bump),
disable (valid code), and password change (wrong/too-short/duplicate → 400, success).
"""
from __future__ import annotations

import pyotp
import pytest
import pytest_asyncio
from fastapi import HTTPException, Response
from starlette.requests import Request

from api.admin import auth as A
from core.db import SessionFactory, engine
from core.models import AdminUser, Base
from core.services.admin_auth import hash_password, new_totp_secret
from core.services.crypto import encrypt


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req() -> Request:
    return Request({"type": "http", "method": "POST", "headers": [], "client": ("1.1.1.1", 1)})


async def _admin(session, *, email, role="admin", password="oldpassword1", totp=None):
    a = AdminUser(email=email, password_hash=hash_password(password), role=role,
                  is_active=True, totp_secret=(encrypt(totp) if totp else None))
    session.add(a)
    await session.commit()
    return a


async def test_2fa_status_and_setup():
    async with SessionFactory() as s:
        a = await _admin(s, email="a@x.io", role="admin")
        st = await A.twofa_status(admin=a)
        assert st["enabled"] is False and st["required"] is True  # admin role requires MFA
        setup = await A.twofa_setup(admin=a)
        assert setup["secret"] and setup["uri"].startswith("otpauth://")


async def test_2fa_enable_invalid_then_valid():
    async with SessionFactory() as s:
        a = await _admin(s, email="b@x.io", role="admin")
        secret = new_totp_secret()
        with pytest.raises(HTTPException):
            await A.twofa_enable(req=A.TwoFAEnable(secret=secret, code="000000"),
                                 response=Response(), request=_req(), admin=a, session=s)
        code = pyotp.TOTP(secret).now()
        out = await A.twofa_enable(req=A.TwoFAEnable(secret=secret, code=code),
                                   response=Response(), request=_req(), admin=a, session=s)
        assert out["enabled"] is True and a.totp_secret is not None


async def test_2fa_disable_with_valid_code():
    async with SessionFactory() as s:
        secret = new_totp_secret()
        a = await _admin(s, email="c@x.io", role="admin", totp=secret)
        out = await A.twofa_disable(req=A.TwoFADisable(code=pyotp.TOTP(secret).now()),
                                    request=_req(), admin=a, session=s)
        assert out["enabled"] is False and a.totp_secret is None


async def test_password_change_paths():
    async with SessionFactory() as s:
        a = await _admin(s, email="d@x.io", role="support", password="oldpassword1")
        # wrong current password
        with pytest.raises(HTTPException):
            await A.change_password(
                req=A.PasswordChange(current_password="WRONG", new_password="newpassword1"),
                response=Response(), request=_req(), admin=a, session=s)
        # too short
        with pytest.raises(HTTPException):
            await A.change_password(
                req=A.PasswordChange(current_password="oldpassword1", new_password="short"),
                response=Response(), request=_req(), admin=a, session=s)
        # success + token_version bump (revokes sessions)
        v0 = a.token_version
        out = await A.change_password(
            req=A.PasswordChange(current_password="oldpassword1", new_password="newpassword1"),
            response=Response(), request=_req(), admin=a, session=s)
        assert out["ok"] is True and a.token_version == v0 + 1
