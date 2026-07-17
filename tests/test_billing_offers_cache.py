"""PERF-A1b: /billing/offers is a global projection of the pricing config, but it
fanned out into ~7 pricing reads (a get_config deserialize per pack + subscription
+ credits) on every Mini App billing-tab open. This asserts the assembled payload
is cached so a cache-warm call issues NO further pricing reads. Staleness is bounded
by the cache TTL and cleared by pricing.set_config on any admin price change."""
from __future__ import annotations

import pytest
import pytest_asyncio

import core.services.pricing as pricing
from api.routers.miniapp import _OFFERS_CACHE_KEY, _billing_offers_payload
from core.db import SessionFactory, engine
from core.models import Base

_CONFIG_CACHE_KEY = "cache:business_config"


@pytest_asyncio.fixture(autouse=True)
async def _tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.mark.asyncio
async def test_billing_offers_cached_across_calls(monkeypatch):
    for key in (_OFFERS_CACHE_KEY, _CONFIG_CACHE_KEY):
        try:
            await pricing.redis_client.delete(key)
        except Exception:
            pass

    calls = {"n": 0}
    real = pricing.get_config

    async def _counting(session):
        calls["n"] += 1
        return await real(session)

    monkeypatch.setattr(pricing, "get_config", _counting)

    async with SessionFactory() as s:
        first = await _billing_offers_payload(s)
        after_first = calls["n"]
        second = await _billing_offers_payload(s)
        after_second = calls["n"]

    assert first == second
    assert after_first >= 1  # first call actually read the pricing config
    assert after_second == after_first, (
        f"_billing_offers_payload re-read pricing on a cache-warm call: "
        f"{after_first} -> {after_second}"
    )
