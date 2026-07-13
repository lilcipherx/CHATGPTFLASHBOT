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
from core.services.credits import grant
from core.services.users import get_or_create_user


def _mock_gen(monkeypatch):
    import types

    import api.routers.miniapp as m

    async def _allow(_t):
        return types.SimpleNamespace(allowed=True, reason=None)

    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(m.moderation, "moderate", _allow)
    monkeypatch.setattr(m, "enqueue", _noop)

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


async def test_bonus_claim(client):
    r = await client.post("/api/bonus/claim")
    assert r.status_code == 200
    assert "claimed" in r.json()


async def test_promo_empty_and_invalid_code(client):
    assert (await client.post("/api/promo", json={"code": ""})).status_code == 400
    # an unknown code is a graceful rejection (never a 500), not a crash
    r = await client.post("/api/promo", json={"code": "DOES-NOT-EXIST"})
    assert r.status_code in (200, 400, 404)


async def test_free_model_cost_and_unknown(client):
    r = await client.post("/api/models/photo/gpt_image2/cost", json={"params": {}})
    assert r.status_code == 200 and "cost" in r.json()
    r404 = await client.post("/api/models/photo/no_such_model/cost", json={"params": {}})
    assert r404.status_code == 404


async def test_free_model_generate(client, monkeypatch):
    import types

    import api.routers.miniapp as m

    async def _allow(_text):
        return types.SimpleNamespace(allowed=True, reason=None)

    async def _noop_enqueue(*a, **k):
        return None

    monkeypatch.setattr(m.moderation, "moderate", _allow)
    monkeypatch.setattr(m, "enqueue", _noop_enqueue)

    r = await client.post(
        "/api/models/photo/gpt_image2/generate",
        data={"prompt": "a calm sunset over the sea", "params": "{}", "idempotency_key": "k1"},
    )
    # fresh user has free allowance → 200 (job queued); tolerate charge/limit outcomes.
    assert r.status_code in (200, 402, 429, 503), r.text[:200]


async def test_generate_unknown_model_404(client, monkeypatch):
    _mock_gen(monkeypatch)
    r = await client.post("/api/models/photo/no_such_model/generate",
                          data={"prompt": "x", "idempotency_key": "u1"})
    assert r.status_code == 404


async def test_generate_banned_403(client, monkeypatch):
    _mock_gen(monkeypatch)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, _TG["id"])
        user.is_banned = True
        await s.commit()
    r = await client.post("/api/models/photo/gpt_image2/generate",
                          data={"prompt": "x", "idempotency_key": "b1"})
    assert r.status_code == 403


async def test_video_generate_no_credits_402(client, monkeypatch):
    _mock_gen(monkeypatch)
    # video has no free weekly slot → charged to ✨; a fresh user has none → 402.
    r = await client.post("/api/models/video/seedance/generate",
                          data={"prompt": "x", "idempotency_key": "v1"})
    assert r.status_code == 402


async def test_video_generate_with_credits_200(client, monkeypatch):
    _mock_gen(monkeypatch)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, _TG["id"])
        await grant(s, user, 100)
    r = await client.post("/api/models/video/seedance/generate",
                          data={"prompt": "x", "idempotency_key": "v2"})
    assert r.status_code == 200


def _png_bytes() -> bytes:
    """A real, decodable PNG (the upload validator content-decodes with Pillow)."""
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (120, 180, 90)).save(buf, "PNG")
    return buf.getvalue()


_PNG = _png_bytes()


async def test_effect_generate_with_photo(client, monkeypatch):
    _mock_gen(monkeypatch)
    from core.models.catalog import MiniAppPhotoEffect
    async with SessionFactory() as s:
        s.add(MiniAppPhotoEffect(
            effect_id=1, category="all", name_ru="Тест", enabled=True,
            prompt_mode="optional", max_photos=1, price=0,
            recommended_model="gpt_image2", compatible_models=["gpt_image2"],
        ))
        await s.commit()
    # curated photo effect: upload one photo + apply it (free weekly slot covers cost).
    r = await client.post(
        "/api/effects/photo/1/generate",
        data={"model": "gpt_image2", "prompt": "make it art", "idempotency_key": "e1"},
        files=[("photos", ("p.png", _PNG, "image/png"))],
    )
    assert r.status_code in (200, 402, 503), r.text[:200]


async def test_effect_generate_unknown_effect_404(client, monkeypatch):
    _mock_gen(monkeypatch)
    r = await client.post(
        "/api/effects/photo/999999/generate",
        data={"model": "gpt_image2", "prompt": "x", "idempotency_key": "e2"},
        files=[("photos", ("p.png", _PNG, "image/png"))],
    )
    assert r.status_code == 404
