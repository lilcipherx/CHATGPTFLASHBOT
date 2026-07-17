"""The Mini App catalog endpoints (/photo-effects, /video-effects, /effects) are
pure reads and now route through get_read_session (→ read replica when configured).
This asserts they are genuinely write-free by pinning the read session to SQLite
``PRAGMA query_only=ON`` — any accidental write in these handlers would raise, so a
200 proves the read-only contract (and guards against a future writing endpoint
being wired to the replica session).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.deps import current_webapp_user
from api.main import app
from core.db import SessionFactory, engine, get_read_session
from core.models import Base, MiniAppPhotoEffect, MiniAppVideoEffect

_TG = {"id": 8888, "username": "cat", "language_code": "en", "first_name": "C"}


@pytest_asyncio.fixture(autouse=True)
async def _setup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionFactory() as s:
        s.add(MiniAppPhotoEffect(effect_id=1, category="all", name_ru="P", enabled=True))
        s.add(MiniAppVideoEffect(
            effect_id=1, category="all", name_ru="V", provider="kie", enabled=True))
        await s.commit()
    app.dependency_overrides[current_webapp_user] = lambda: dict(_TG)

    # Force the read session strictly read-only: a write would raise, so a 200 proves
    # the handler only reads.
    async def _readonly():
        async with SessionFactory() as s:
            await s.execute(text("PRAGMA query_only=ON"))
            yield s

    app.dependency_overrides[get_read_session] = _readonly
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/photo-effects",
    "/api/video-effects",
    "/api/effects?kind=photo&category=all",
    "/api/effects?kind=video&category=all",
    "/api/effects?kind=photo&trending=true",
])
async def test_catalog_endpoint_is_read_only(path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(path)
    assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"
    assert isinstance(r.json(), list)
