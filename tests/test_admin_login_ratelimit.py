"""Admin login must rate-limit per source IP (brute-force defence in depth).

The /api/admin/auth/login endpoint already gates on slow argon2 + mandatory TOTP,
but had no cap on attempt volume. This guards the fixed-window IP limiter: after
the 30/5-min allowance is spent, further attempts get 429 BEFORE any credential
work — so a script can't grind passwords/OTPs.

The endpoint coroutine is invoked directly (rather than via TestClient) so the whole
test runs in one event loop — the fakeredis singleton binds its pool to that loop,
which a multi-loop TestClient would break (the limiter would then fail open).
"""
from __future__ import annotations

import pytest_asyncio
from fastapi import HTTPException, Response
from starlette.requests import Request

from api.admin.auth import LoginRequest, login
from core.db import SessionFactory, engine
from core.models import Base
from core.redis_client import redis_client


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _make_request(ip: str = "9.9.9.9") -> Request:
    return Request({"type": "http", "method": "POST", "headers": [], "client": (ip, 1234)})


async def _attempt() -> int:
    req = LoginRequest(email="nobody@example.com", password="wrong", otp=None)
    async with SessionFactory() as s:
        try:
            await login(req=req, response=Response(), request=_make_request(), session=s)
            return 200
        except HTTPException as exc:
            return exc.status_code


async def test_login_is_rate_limited_per_ip():
    await redis_client.flushdb()
    # First 30 reach the credential check and bounce as 401 (unknown email).
    for _ in range(30):
        assert await _attempt() == 401
    # The 31st from the same IP is over the window → rejected before credential work.
    assert await _attempt() == 429
