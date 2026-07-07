"""Time-limited global sale (ТЗ §4): a live discount applied across every price
getter, so bot keyboards / Mini App invoices / checkout all reflect it. Default
off (percent 0) — no behaviour change until an admin enables it.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base
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


async def test_no_sale_by_default():
    async with SessionFactory() as s:
        assert await pricing.subscription_price(s, "premium", 1) == 600
        assert await pricing.credit_pack_price(s, 100) == 250
        assert await pricing.avatar_price(s) == 200
        assert (await pricing.sale_state(s))["active"] is False


async def test_active_sale_discounts_all_surfaces():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"sale": {"percent": 50, "until": None}})
    async with SessionFactory() as s:
        assert await pricing.subscription_price(s, "premium", 1) == 300   # 600 -50%
        assert await pricing.pack_price(s, "image_pack", 50) == 125       # 250 -50%
        assert await pricing.credit_pack_price(s, 100) == 125            # 250 -50%
        assert await pricing.avatar_price(s) == 100                      # 200 -50%
        # keyboard maps are discounted too
        assert (await pricing.subscription_prices(s, "premium"))[12] == 1500  # 3000 -50%
        assert (await pricing.credit_packs(s))[500] == 500              # 1000 -50%
        st = await pricing.sale_state(s)
        assert st["active"] is True and st["percent"] == 50


async def test_expired_sale_is_ignored():
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    async with SessionFactory() as s:
        await pricing.set_config(s, {"sale": {"percent": 50, "until": past}})
    async with SessionFactory() as s:
        assert await pricing.subscription_price(s, "premium", 1) == 600  # no discount
        assert (await pricing.sale_state(s))["active"] is False


async def test_future_until_applies():
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    async with SessionFactory() as s:
        await pricing.set_config(s, {"sale": {"percent": 20, "until": future}})
    async with SessionFactory() as s:
        assert await pricing.subscription_price(s, "premium", 1) == 480  # 600 -20%
        assert (await pricing.sale_state(s))["active"] is True


async def test_percent_capped_and_price_never_zero():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"sale": {"percent": 100, "until": None}})
    async with SessionFactory() as s:
        # capped at 95% -> 600 * 5% = 30, and never below 1
        assert await pricing.subscription_price(s, "premium", 1) == 30
        assert await pricing.avatar_price(s) >= 1


# ---- scheduled start (from) -------------------------------------------------
async def test_scheduled_from_not_started_yet():
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    async with SessionFactory() as s:
        await pricing.set_config(s, {"sale": {"percent": 30, "from": future, "until": None}})
    async with SessionFactory() as s:
        # not started -> full price, but reported as scheduled (not active)
        assert await pricing.subscription_price(s, "premium", 1) == 600
        assert await pricing.sale_percent(s) == 0
        st = await pricing.sale_state(s)
        assert st["active"] is False and st["scheduled"] is True


async def test_scheduled_from_already_started():
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    async with SessionFactory() as s:
        await pricing.set_config(s, {"sale": {"percent": 30, "from": past, "until": None}})
    async with SessionFactory() as s:
        assert await pricing.subscription_price(s, "premium", 1) == 420  # 600 -30%
        assert await pricing.sale_percent(s) == 30
        st = await pricing.sale_state(s)
        assert st["active"] is True and st["scheduled"] is False


async def test_from_window_and_until_combined():
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    expired = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    async with SessionFactory() as s:
        await pricing.set_config(s, {"sale": {"percent": 30, "from": past, "until": expired}})
    async with SessionFactory() as s:
        # started but already past its end -> off (and not "scheduled")
        assert await pricing.subscription_price(s, "premium", 1) == 600
        st = await pricing.sale_state(s)
        assert st["active"] is False and st["scheduled"] is False


# ---- pre-sale price maps for keyboards --------------------------------------
async def test_apply_sale_false_returns_presale_prices():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"sale": {"percent": 50, "until": None}})
    async with SessionFactory() as s:
        # discounted by default; raw when apply_sale=False (keyboards show both)
        assert (await pricing.subscription_prices(s, "premium"))[1] == 300
        assert (await pricing.subscription_prices(s, "premium", apply_sale=False))[1] == 600
        assert (await pricing.credit_packs(s, apply_sale=False))[100] == 250
