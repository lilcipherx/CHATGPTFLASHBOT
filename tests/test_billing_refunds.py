"""Billing refund/revoke paths (Loop coverage, money-critical): peek the refundable
Stars charge, idempotent mark_stars_refunded (entitlement reversal at most once), and
revoke_entitlement clamping for credits + premium. DB only.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base
from core.services import billing
from core.services.credits import get_balance
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_peek_and_mark_stars_refunded_credits():
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 6001)
        ok = await billing.add_credits(
            s, user, qty=10, gateway="stars", amount=100, gateway_tx_id="star_1"
        )
        assert ok and await get_balance(s, 6001) == 10

        # peek finds the paid non-refunded Stars charge for this product.
        cid = await billing.peek_refundable_stars_tx(s, 6001, "credits")
        assert cid == "star_1"

        # mark refunded → reverses the 10 credits and flips status; idempotent.
        assert await billing.mark_stars_refunded(s, "star_1") is True
        assert await get_balance(s, 6001) == 0
        assert await billing.mark_stars_refunded(s, "star_1") is False
        # nothing left to refund now
        assert await billing.peek_refundable_stars_tx(s, 6001, "credits") is None


async def test_peek_by_exact_charge_id():
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 6002)
        await billing.add_credits(s, user, qty=5, gateway="stars", amount=50,
                                  gateway_tx_id="star_a")
        await billing.add_credits(s, user, qty=5, gateway="stars", amount=50,
                                  gateway_tx_id="star_b")
        # exact charge id wins over "newest of product"
        assert await billing.peek_refundable_stars_tx(s, 6002, "credits", "star_a") == "star_a"
        # unknown charge id → nothing
        assert await billing.peek_refundable_stars_tx(s, 6002, "credits", "nope") is None


async def test_revoke_entitlement_premium_clears_sub():
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 6003)
        ok = await billing.activate_subscription(
            s, user, product="premium", months=1, gateway="stars", amount=100,
            gateway_tx_id="star_sub",
        )
        assert ok and user.sub_expires is not None
        # refunding the 1-month sub pulls expiry back below now → tier cleared.
        assert await billing.mark_stars_refunded(s, "star_sub") is True
        await s.refresh(user)
        assert user.sub_expires is None and user.sub_tier is None
