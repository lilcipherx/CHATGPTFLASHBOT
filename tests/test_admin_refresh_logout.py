"""Admin token refresh + logout (Loop coverage, auth-critical). Direct coroutine calls
with a seeded admin: refresh issues a new session for a valid refresh token and rejects
missing/wrong-type/revoked tokens; logout bumps token_version (revoke-all).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import HTTPException, Response
from starlette.requests import Request

from api.admin.auth import RefreshRequest, logout, refresh
from core.db import SessionFactory, engine
from core.models import AdminUser, Base
from core.services.admin_auth import create_token, hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req() -> Request:
    return Request({"type": "http", "method": "POST", "headers": [], "client": ("1.1.1.1", 1)})


async def _admin(session, email="r@x.io"):
    a = AdminUser(email=email, password_hash=hash_password("x"), role="admin", is_active=True)
    session.add(a)
    await session.commit()
    return a


async def test_refresh_valid_issues_session():
    async with SessionFactory() as s:
        a = await _admin(s)
        tok = create_token(a.id, a.role, refresh=True, ver=a.token_version)
        res = await refresh(response=Response(), request=_req(),
                            req=RefreshRequest(refresh_token=tok), _=None, session=s)
        assert res.role == "admin"


async def test_refresh_rejects_access_token_and_missing():
    async with SessionFactory() as s:
        a = await _admin(s, email="r2@x.io")
        # an ACCESS token presented to /refresh → 401 (wrong type)
        access = create_token(a.id, a.role, ver=a.token_version)
        with pytest.raises(HTTPException) as e1:
            await refresh(response=Response(), request=_req(),
                          req=RefreshRequest(refresh_token=access), _=None, session=s)
        assert e1.value.status_code == 401
        # no token at all → 401
        with pytest.raises(HTTPException) as e2:
            await refresh(response=Response(), request=_req(), req=None, _=None, session=s)
        assert e2.value.status_code == 401


async def test_refresh_revoked_version_rejected():
    async with SessionFactory() as s:
        a = await _admin(s, email="r3@x.io")
        stale = create_token(a.id, a.role, refresh=True, ver=a.token_version)
        a.token_version += 1  # a logout/password-change elsewhere revoked it
        await s.commit()
        with pytest.raises(HTTPException) as e:
            await refresh(response=Response(), request=_req(),
                          req=RefreshRequest(refresh_token=stale), _=None, session=s)
        assert e.value.status_code == 401


async def test_logout_bumps_token_version():
    async with SessionFactory() as s:
        a = await _admin(s, email="lo@x.io")
        v0 = a.token_version
        out = await logout(response=Response(), request=_req(), admin=a, session=s)
        assert out["ok"] is True and a.token_version == v0 + 1
