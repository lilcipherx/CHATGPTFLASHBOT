"""Mini App quota math (limits now live-configurable) + API surface."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from core.constants import MINIAPP_PHOTO_COST
from core.db import SessionFactory, engine
from core.models import Base, User
from core.services import pricing, quota


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
    try:
        await pricing.redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


def _user(**kw) -> User:
    u = User(user_id=1, language_code="ru")
    for k, v in kw.items():
        setattr(u, k, v)
    return u


async def test_free_miniapp_weekly_limit_25():
    u = _user(mini_app_effects_week=25, mini_app_week_start=datetime.now(UTC))
    async with SessionFactory() as s:
        st = await quota.miniapp_quota_state(s, u)
    assert st.limit == 25 and st.allowed is False


async def test_premium_miniapp_daily_limit():
    u = _user(
        sub_tier="premium",
        sub_expires=datetime.now(UTC) + timedelta(days=5),
        mini_app_effects_week=0,
        mini_app_week_start=datetime.now(UTC),
    )
    async with SessionFactory() as s:
        st = await quota.miniapp_quota_state(s, u)
    assert st.limit == 100 and st.is_premium is True


async def test_miniapp_limit_admin_override():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"limits": {"free_miniapp_weekly": 9}})
    u = _user(mini_app_effects_week=0, mini_app_week_start=datetime.now(UTC))
    async with SessionFactory() as s:
        st = await quota.miniapp_quota_state(s, u)
    assert st.limit == 9


async def test_photo_cost_by_quality():
    assert MINIAPP_PHOTO_COST == {"1k": 2, "2k": 3, "4k": 4}


async def test_api_has_miniapp_routes():
    from api.main import app

    paths = {r.path for r in app.routes}
    assert "/api/video-effects" in paths
    # Unified Higgsfield generate path (the legacy /effects/generate and
    # /video-effects/generate endpoints were removed — dead, unused by the app).
    assert "/api/effects/{kind}/{effect_id}/generate" in paths
    assert "/api/effects/generate" not in paths
    assert "/api/video-effects/generate" not in paths
    assert "/api/jobs" in paths
    assert "/api/jobs/{job_id}" in paths
    assert "/api/billing/invoice-link" in paths
