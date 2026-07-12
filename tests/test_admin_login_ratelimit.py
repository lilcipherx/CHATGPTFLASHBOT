"""Admin login brute-force defence in depth: per-IP AND per-account caps.

The /api/admin/auth/login endpoint gates on slow argon2 + mandatory TOTP, but that
alone doesn't cap attempt volume:

* the fixed-window IP limiter (30/5min) stops one source grinding many accounts;
* the per-account failure lockout (AUDIT-A1, 10 failures/15min, reset on success)
  stops a distributed/rotating-IP attacker grinding ONE account — the case the IP
  limiter misses, and the most dangerous for a support/moderator without 2FA.

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


async def _attempt(email: str = "nobody@example.com", ip: str = "9.9.9.9") -> int:
    req = LoginRequest(email=email, password="wrong", otp=None)
    async with SessionFactory() as s:
        try:
            await login(req=req, response=Response(), request=_make_request(ip), session=s)
            return 200
        except HTTPException as exc:
            return exc.status_code


async def test_login_is_rate_limited_per_ip():
    await redis_client.flushdb()
    # Many accounts probed from ONE IP: the first 30 reach the credential check and
    # bounce as 401 (unknown email); a UNIQUE email each time keeps the per-account
    # counter from tripping first, isolating the IP cap.
    for i in range(30):
        assert await _attempt(email=f"u{i}@example.com") == 401
    # The 31st from the same IP is over the window → rejected before credential work.
    assert await _attempt(email="u999@example.com") == 429


async def test_login_is_locked_out_per_account_across_ips():
    await redis_client.flushdb()
    # ONE account ground from 10 DIFFERENT source IPs (so the per-IP cap never trips).
    for i in range(10):
        assert await _attempt(email="victim@example.com", ip=f"10.0.0.{i}") == 401
    # The 11th attempt on the same account — even from a fresh IP — is locked out.
    assert await _attempt(email="victim@example.com", ip="10.0.0.99") == 429
