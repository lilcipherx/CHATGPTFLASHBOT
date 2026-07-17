"""Mini App effect segments (photo/video) are provider-aware + admin-overridable
(ТЗ §13): "auto" shows a segment only when a working provider exists for its
modality (a Kie/MuAPI aggregator account OR a direct env-key adapter); "on"/"off"
force it. The /profile response carries the result so the app hides a kind that
can only refund.
"""
from __future__ import annotations

import pytest_asyncio

import api.routers.miniapp as miniapp
from core.db import SessionFactory, engine
from core.models import Base
from core.models.ai_routing import AIAccount
from core.services import pricing


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield


async def _sections() -> dict:
    # PERF-A1: _miniapp_sections is now Redis-cached (fakeredis is a process
    # singleton), so clear both the sections cache AND the business-config cache
    # it derives from immediately before computing — these tests assert the live
    # compute path, not cache reuse, and must not see a value another test left.
    for key in (miniapp._SECTIONS_CACHE_KEY, pricing._CACHE_KEY):
        try:
            await pricing.redis_client.delete(key)
        except Exception:  # noqa: BLE001
            pass
    async with SessionFactory() as s:
        return await miniapp._miniapp_sections(s)


async def test_admin_on_off_override(monkeypatch):
    monkeypatch.setattr(miniapp, "_direct_provider_available", lambda kind: False)
    async with SessionFactory() as s:
        await pricing.set_config(s, {"miniapp_sections": {"photo": "on", "video": "off"}})
    assert await _sections() == {"photo": True, "video": False}


async def test_auto_hidden_without_any_provider(monkeypatch):
    monkeypatch.setattr(miniapp, "_direct_provider_available", lambda kind: False)
    assert await _sections() == {"photo": False, "video": False}


async def test_auto_shows_with_aggregator_account(monkeypatch):
    monkeypatch.setattr(miniapp, "_direct_provider_available", lambda kind: False)
    async with SessionFactory() as s:
        s.add(AIAccount(name="Kie img", kind="kie", base_url="https://api.kie.ai",
                        api_key="x", modality="image", enabled=True))
        await s.commit()
    out = await _sections()
    assert out["photo"] is True       # image aggregator → photo segment shown
    assert out["video"] is False      # no video provider


async def test_auto_shows_with_direct_adapter(monkeypatch):
    # Only the video direct adapter reports available → only video shows.
    monkeypatch.setattr(miniapp, "_direct_provider_available", lambda kind: kind == "video")
    out = await _sections()
    assert out["video"] is True
    assert out["photo"] is False
