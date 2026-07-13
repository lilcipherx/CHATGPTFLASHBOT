"""Admin login success paths (Loop coverage, auth-critical). Complements
test_admin_login_ratelimit.py (which only drives the 401/429 failure caps) by covering
the full-token issue, the mfa-setup handshake for a 2FA-required role, OTP-required /
OTP-valid, and a wrong password. login() is invoked directly so the whole test shares
one event loop (the fakeredis limiter binds its pool to it).
"""
from __future__ import annotations

import pyotp
import pytest_asyncio
from fastapi import HTTPException, Response
from starlette.requests import Request

from api.admin.auth import LoginRequest, login
from core.db import SessionFactory, engine
from core.models import AdminUser, Base
from core.redis_client import redis_client
from core.services.admin_auth import hash_password, new_totp_secret
from core.services.crypto import encrypt


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await redis_client.flushdb()
    yield


def _req(ip: str = "7.7.7.7") -> Request:
    return Request({"type": "http", "method": "POST", "headers": [], "client": (ip, 1234)})


async def _mk_admin(session, *, email, role, password="pw-correct-123", totp_secret=None):
    a = AdminUser(
        email=email, password_hash=hash_password(password), role=role, is_active=True,
        totp_secret=(encrypt(totp_secret) if totp_secret else None),
    )
    session.add(a)
    await session.commit()
    return a


async def _login(session, email, *, password="pw-correct-123", otp=None, ip="7.7.7.7"):
    return await login(req=LoginRequest(email=email, password=password, otp=otp),
                       response=Response(), request=_req(ip), session=session)


async def test_support_correct_password_no_2fa_full_token():
    async with SessionFactory() as s:
        await _mk_admin(s, email="support@x.io", role="support")
    async with SessionFactory() as s:
        res = await _login(s, "support@x.io")
    # support is not in mfa_required_roles → a full session, no 2FA handshake.
    assert res.access_token and res.mfa_setup_required is False
    assert res.role == "support"


async def test_admin_role_without_2fa_gets_mfa_setup():
    async with SessionFactory() as s:
        await _mk_admin(s, email="admin@x.io", role="admin")
    async with SessionFactory() as s:
        res = await _login(s, "admin@x.io", ip="7.7.7.8")
    # admin REQUIRES 2FA but hasn't enrolled → restricted mfa_setup session.
    assert res.mfa_setup_required is True and res.access_token


async def test_wrong_password_401():
    async with SessionFactory() as s:
        await _mk_admin(s, email="sup2@x.io", role="support")
    async with SessionFactory() as s:
        try:
            await _login(s, "sup2@x.io", password="WRONG", ip="7.7.7.9")
            raise AssertionError("expected 401")
        except HTTPException as e:
            assert e.status_code == 401


async def test_totp_required_then_valid():
    secret = new_totp_secret()
    async with SessionFactory() as s:
        await _mk_admin(s, email="mod@x.io", role="moderator", totp_secret=secret)

    # OTP required when a secret is enrolled.
    async with SessionFactory() as s:
        try:
            await _login(s, "mod@x.io", ip="7.7.7.10")
            raise AssertionError("expected otp_required")
        except HTTPException as e:
            assert e.status_code == 401

    # A valid current OTP → full token.
    async with SessionFactory() as s:
        code = pyotp.TOTP(secret).now()
        res = await _login(s, "mod@x.io", otp=code, ip="7.7.7.11")
    assert res.access_token and res.mfa_setup_required is False
