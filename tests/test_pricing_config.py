"""Live business-config engine (core/services/pricing) — ТЗ §1 foundation.

Verifies prices/limits fall back to the static defaults, that an admin override
(stored in the `pricing` KV table) is read live, and that unknown keys are ignored.
"""
from __future__ import annotations

import pytest_asyncio

from core.constants import SUBSCRIPTION_PRICES
from core.db import SessionFactory, engine
from core.models import Base
from core.services import pricing


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    # Reset the Redis cache so overrides from a prior test don't leak.
    try:
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield
    # fakeredis caches a connection bound to THIS test's event loop; drop it so the
    # next test (a fresh loop) reconnects cleanly instead of hitting "bound to a
    # different event loop".
    try:
        await pricing.redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


async def test_defaults_when_no_override():
    async with SessionFactory() as s:
        d = pricing.defaults()
        lim = await pricing.limits(s)
        assert lim == d["limits"]
        # a known default subscription price (premium 1 month)
        assert await pricing.subscription_price(s, "premium", 1) == \
            SUBSCRIPTION_PRICES["premium"][1]
        assert await pricing.avatar_price(s) == d["avatar_price"]


async def test_admin_override_applies_live():
    async with SessionFactory() as s:
        await pricing.set_config(s, {
            "limits": {"free_text_weekly": 7},
            "subscription_prices": {"premium": {"1": 999}},
            "avatar_price": 321,
        })
    async with SessionFactory() as s:
        lim = await pricing.limits(s)
        assert lim["free_text_weekly"] == 7
        # other limits keep their defaults (deep-merge)
        assert lim["premium_daily"] == pricing.defaults()["limits"]["premium_daily"]
        assert await pricing.subscription_price(s, "premium", 1) == 999
        assert await pricing.avatar_price(s) == 321


async def test_unknown_key_rejected():
    async with SessionFactory() as s:
        cfg = await pricing.set_config(s, {"__evil__": 1, "avatar_price": 5})
        assert "__evil__" not in cfg
        assert cfg["avatar_price"] == 5


async def test_missing_product_returns_none():
    async with SessionFactory() as s:
        assert await pricing.subscription_price(s, "nope", 1) is None
        assert await pricing.pack_price(s, "nope", 1) is None
        assert await pricing.credit_pack_price(s, 99999) is None


async def test_price_maps_reflect_overrides_with_int_keys():
    async with SessionFactory() as s:
        await pricing.set_config(s, {
            "subscription_prices": {"premium": {"1": 100}},
            "pack_prices": {"image_pack": {"50": 200}},
            "credit_packs": {"100": 300},
        })
    async with SessionFactory() as s:
        subs = await pricing.subscription_prices(s, "premium")
        assert subs[1] == 100  # overridden, int key (for keyboards)
        # untouched months keep their defaults (deep-merge)
        assert subs[3] == SUBSCRIPTION_PRICES["premium"][3]
        assert (await pricing.pack_prices_for(s, "image_pack"))[50] == 200
        assert (await pricing.credit_packs(s))[100] == 300
