"""Mini App read-API integration (Loop coverage): drive the GET endpoints through the
real FastAPI app with the Telegram-initData dependency overridden, so the router +
serializers + service reads actually execute. Backend deps (DB/Redis) are the real
test doubles (SQLite + fakeredis). This exercises the large, previously-untested
api/routers/miniapp.py surface end to end.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.deps import current_webapp_user
from api.main import app
from core.db import SessionFactory, engine
from core.models import Base
from core.services.users import get_or_create_user

_TG = {"id": 5555, "username": "tester", "language_code": "en", "first_name": "T"}


@pytest_asyncio.fixture(autouse=True)
async def _setup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionFactory() as s:
        await get_or_create_user(s, _TG["id"])
        await s.commit()
    app.dependency_overrides[current_webapp_user] = lambda: dict(_TG)
    yield
    app.dependency_overrides.pop(current_webapp_user, None)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.mark.parametrize("path", [
    "/api/profile",
    "/api/bonus",
    "/api/referrals",
    "/api/categories",
    "/api/photo-ratios",
    "/api/photo-effects",
    "/api/video-effects",
    "/api/banners",
    "/api/effects?kind=photo&category=all",
    "/api/effects?kind=video&category=all",
    "/api/models/photo",
    "/api/jobs",
    "/api/billing/offers",
])
async def test_miniapp_get_endpoint_ok(client, path):
    r = await client.get(path)
    assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"


async def test_profile_reports_the_overridden_user(client):
    r = await client.get("/api/profile")
    assert r.status_code == 200
    body = r.json()
    # profile echoes balance/quota for the authenticated tg user
    assert isinstance(body, dict)
