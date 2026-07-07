"""Mini App storefront (/billing/offers) is a pure projection of admin config:
which credit/pack/Premium offers to show + their live Stars prices. The Mini App
renders THIS instead of hard-coding qty/months arrays (ТЗ §4/§11), so the admin
controls the store without a frontend release.

Covered: defaults are exposed; an admin-added qty appears; a 0 price hides an
offer; a global sale discounts the shown prices.
"""
from __future__ import annotations

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
    except Exception:  # noqa: BLE001 — cache is best-effort
        pass
    yield


async def _offers(uid: int = 1) -> dict:
    from api.routers.miniapp import billing_offers

    async with SessionFactory() as s:
        return await billing_offers(
            tg={"id": uid, "username": "u", "language_code": "ru"}, session=s
        )


async def test_defaults_exposed():
    out = await _offers()
    assert {o["qty"] for o in out["credits"]} == {100, 500, 1000}
    assert {o["months"] for o in out["premium"]} == {1, 3, 6, 12}
    for pack in ("image_pack", "video_pack", "music_pack"):
        assert out["packs"][pack], f"{pack} should have offers"
    # every shown offer carries a positive Stars price
    assert all(o["stars"] > 0 for o in out["credits"])
    assert all(o["stars"] > 0 for o in out["premium"])


async def test_admin_added_qty_appears():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"credit_packs": {"777": 1500}})
    out = await _offers()
    by_qty = {o["qty"]: o["stars"] for o in out["credits"]}
    assert by_qty.get(777) == 1500          # new offer surfaced
    assert 100 in by_qty                     # deep-merge keeps the defaults too


async def test_zero_price_hides_offer():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"credit_packs": {"100": 0}})
    out = await _offers()
    qtys = {o["qty"] for o in out["credits"]}
    assert 100 not in qtys                    # price 0 == removed from the storefront
    assert {500, 1000} <= qtys


async def test_sale_discounts_shown_prices():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"sale": {"percent": 50, "until": None}})
    out = await _offers()
    c100 = next(o for o in out["credits"] if o["qty"] == 100)
    assert c100["stars"] == 125               # 250 default, -50%
