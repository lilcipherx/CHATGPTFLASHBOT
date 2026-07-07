"""VIP / loyalty levels (ТЗ §4): auto-tier by cumulative spend + quota bonuses.

Disabled by default (no behaviour change). Driven by live business_config.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, Transaction
from core.services import loyalty, pricing
from core.services.quota import daily_limit, text_quota_state
from core.services.users import get_or_create_user


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


async def _user(session, uid=1, premium=False):
    user, _ = await get_or_create_user(session, uid, username="u")
    if premium:
        user.sub_tier = "premium"
        from datetime import UTC, datetime, timedelta
        user.sub_expires = datetime.now(UTC) + timedelta(days=30)
        await session.commit()
    return user


async def _paid(session, uid, amount, gateway="stars"):
    session.add(Transaction(
        user_id=uid, product="credits", gateway=gateway, amount=amount,
        currency="stars" if gateway == "stars" else "rub", status="paid",
    ))
    await session.commit()


async def test_vip_disabled_by_default():
    async with SessionFactory() as s:
        user = await _user(s)
        await _paid(s, user.user_id, 9999)
        assert await loyalty.tier_for(s, user) is None
        assert await loyalty.vip_bonus(s, user) == (0, 0)


async def test_tier_assigned_by_spend():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"vip": {"enabled": True}})
    async with SessionFactory() as s:
        user = await _user(s)
        # spend 2500 stars -> Silver (min 2000), not yet Gold (5000)
        await _paid(s, user.user_id, 2500)
        tier = await loyalty.tier_for(s, user)
        assert tier is not None and tier["name"] == "Silver"
        assert await loyalty.vip_bonus(s, user) == (20, 50)

        # cross the Gold threshold
        await _paid(s, user.user_id, 3000)  # cumulative 5500
        tier = await loyalty.tier_for(s, user)
        assert tier["name"] == "Gold"


async def test_spend_normalises_fiat_to_stars():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"vip": {"enabled": True}})
    async with SessionFactory() as s:
        user = await _user(s)
        # a RUB purchase in minor units (kopecks) is converted back to stars-equiv
        from core.config import settings
        kopecks = int(round(2500 * settings.stars_to_rub * 100))  # ~2500 stars worth
        await _paid(s, user.user_id, kopecks, gateway="yookassa")
        spent = await loyalty.total_spend_stars(s, user.user_id)
        assert abs(spent - 2500) <= 2  # rounding tolerance
        assert (await loyalty.tier_for(s, user))["name"] == "Silver"


async def test_vip_bonus_raises_premium_daily_limit():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"vip": {"enabled": True}})
    async with SessionFactory() as s:
        user = await _user(s, premium=True)
        base = (await pricing.limits(s))["premium_daily"]
        await _paid(s, user.user_id, 2500)  # Silver -> +20/day
        assert await daily_limit(s, user) == base + 20


async def test_vip_bonus_raises_free_weekly_limit():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"vip": {"enabled": True}})
    async with SessionFactory() as s:
        user = await _user(s)  # free
        base = (await pricing.limits(s))["free_text_weekly"]
        await _paid(s, user.user_id, 5500)  # Gold -> +150/week
        state = await text_quota_state(s, user)
        assert state.limit == base + 150


# ---- progress (account display) ---------------------------------------------
async def test_progress_none_when_disabled():
    async with SessionFactory() as s:
        user = await _user(s)
        assert await loyalty.progress(s, user) is None


async def test_progress_reports_current_and_next():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"vip": {"enabled": True}})
    async with SessionFactory() as s:
        user = await _user(s)
        await _paid(s, user.user_id, 2500)  # Silver(2000), next Gold(5000)
        prog = await loyalty.progress(s, user)
        assert prog["current"]["name"] == "Silver"
        assert prog["next"]["name"] == "Gold"
        assert prog["to_next"] == 2500  # 5000 - 2500


async def test_progress_top_tier_has_no_next():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"vip": {"enabled": True}})
    async with SessionFactory() as s:
        user = await _user(s)
        await _paid(s, user.user_id, 9000)  # past Gold (top)
        prog = await loyalty.progress(s, user)
        assert prog["current"]["name"] == "Gold"
        assert prog["next"] is None and prog["to_next"] == 0


# ---- upgrade notification (idempotent per tier) -----------------------------
async def test_upgrade_notify_once_per_tier():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"vip": {"enabled": True}})
    async with SessionFactory() as s:
        user = await _user(s)
        await _paid(s, user.user_id, 2500)  # Silver
        # get_bot isn't configured under tests -> DM is best-effort (swallowed); the
        # UsageLog claim still happens, which is what idempotency hinges on.
        first = await loyalty.check_and_notify_upgrade(s, user)
        assert first is not None and first["name"] == "Silver"
    async with SessionFactory() as s:
        user = await _user(s)
        # same tier again -> no second congratulation
        assert await loyalty.check_and_notify_upgrade(s, user) is None
    async with SessionFactory() as s:
        user = await _user(s)
        await _paid(s, user.user_id, 3000)  # cumulative 5500 -> Gold (new tier)
        second = await loyalty.check_and_notify_upgrade(s, user)
        assert second is not None and second["name"] == "Gold"


async def test_upgrade_notify_noop_when_disabled():
    async with SessionFactory() as s:
        user = await _user(s)
        await _paid(s, user.user_id, 9999)
        assert await loyalty.check_and_notify_upgrade(s, user) is None
