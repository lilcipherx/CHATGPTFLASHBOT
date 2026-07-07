"""The global OpenAI base-URL setter (admin /provider-base-url) must apply the
same SSRF defence as the per-account base_url setter — a prefix check alone let a
superadmin point the OpenAI client (which sends the API key in the Authorization
header) at an internal/metadata host or an attacker domain, leaking the key.

Calls the endpoint coroutine directly against a seeded SQLite DB.
"""
from __future__ import annotations

import types

import pytest
import pytest_asyncio
from fastapi import HTTPException

from api.admin.ops import OpenAIBaseUrlReq, set_openai_base_url
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
    return types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))


async def _admin(s) -> AdminUser:
    a = AdminUser(email="root@x.io", password_hash=hash_password("x"),
                  role="superadmin", is_active=True)
    s.add(a)
    await s.commit()
    await s.refresh(a)
    return a


@pytest.mark.parametrize("bad", [
    "http://169.254.169.254/v1",   # cloud metadata (link-local)
    "http://127.0.0.1:8000/v1",    # loopback
    "http://10.1.2.3/v1",          # private
    "ftp://api.openai.com/v1",     # wrong scheme
])
async def test_ssrf_urls_rejected(bad):
    async with SessionFactory() as s:
        admin = await _admin(s)
        with pytest.raises(HTTPException) as ei:
            await set_openai_base_url(
                OpenAIBaseUrlReq(url=bad), _req(), admin=admin, session=s,
            )
        assert ei.value.status_code == 400


async def test_public_https_accepted():
    async with SessionFactory() as s:
        admin = await _admin(s)
        out = await set_openai_base_url(
            OpenAIBaseUrlReq(url="https://api.openai.com/v1/"), _req(),
            admin=admin, session=s,
        )
        assert out["ok"] is True
        assert out["value"] == "https://api.openai.com/v1"


async def test_blank_reverts_without_validation():
    async with SessionFactory() as s:
        admin = await _admin(s)
        out = await set_openai_base_url(
            OpenAIBaseUrlReq(url=""), _req(), admin=admin, session=s,
        )
        assert out["ok"] is True


async def test_allowlist_enforced(monkeypatch):
    from api.admin import ai_routing

    monkeypatch.setattr(
        type(ai_routing.settings), "ai_base_url_allow",
        property(lambda self: ["omniroute", "api.openai.com"]),
    )
    async with SessionFactory() as s:
        admin = await _admin(s)
        # host in the allowlist passes even though it's an internal name
        out = await set_openai_base_url(
            OpenAIBaseUrlReq(url="http://omniroute:20128"), _req(),
            admin=admin, session=s,
        )
        assert out["ok"] is True
        # a public host NOT in the allowlist is now rejected
        with pytest.raises(HTTPException) as ei:
            await set_openai_base_url(
                OpenAIBaseUrlReq(url="https://evil.example.com"), _req(),
                admin=admin, session=s,
            )
        assert ei.value.status_code == 400
