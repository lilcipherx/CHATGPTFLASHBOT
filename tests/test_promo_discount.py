"""Discount promo codes (ТЗ §4): a /promo code applied to the account that takes a
%-off the NEXT purchase (max with the global sale, no stacking), spent only on a
successful payment.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, PromoCode, User
from core.services import pricing, promos
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
    try:
        await pricing.redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


async def _code(session, code="SAVE20", pct=20, max_uses=5, new_user_days=0):
    session.add(PromoCode(
        code=code, reward_type="discount", reward_amount=pct,
        max_uses=max_uses, used=0, is_active=True, new_user_days=new_user_days,
    ))
    await session.commit()


# ---- apply (no slot consumed) ----------------------------------------------
async def test_apply_sets_code_without_consuming():
    async with SessionFactory() as s:
        await _code(s)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 1)
        res = await promos.redeem(s, user, "save20")  # case-insensitive
        assert res.ok and res.status == "applied" and res.amount == 20
        assert user.discount_code == "SAVE20"
        promo = await s.get(PromoCode, "SAVE20")
        assert promo.used == 0  # not spent yet — only applied


async def test_active_discount_and_checkout_percent():
    async with SessionFactory() as s:
        await _code(s, pct=20)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 2)
        await promos.redeem(s, user, "SAVE20")
        assert await promos.active_discount(s, user) == 20
        assert await promos.checkout_percent(s, user) == 20
    # with a bigger sale, checkout takes the larger (no stacking)
    async with SessionFactory() as s:
        await pricing.set_config(s, {"sale": {"percent": 30, "until": None}})
    async with SessionFactory() as s:
        user = await s.get(User, 2)
        assert await promos.checkout_percent(s, user) == 30


async def test_discount_price_applied_at_checkout():
    async with SessionFactory() as s:
        await _code(s, pct=25)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 3)
        await promos.redeem(s, user, "SAVE20")
        # premium 1mo base 600 -> -25% = 450
        base = await pricing.subscription_price(s, "premium", 1, apply_sale=False)
        price = pricing.discount(base, await promos.checkout_percent(s, user))
        assert base == 600 and price == 450


# ---- consume on payment -----------------------------------------------------
async def test_consume_spends_slot_when_beats_sale():
    async with SessionFactory() as s:
        await _code(s, pct=20)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 4)
        await promos.redeem(s, user, "SAVE20")
        spent = await promos.consume_discount(s, user, sale_pct=0)
        assert spent == 20
        assert user.discount_code is None
        promo = await s.get(PromoCode, "SAVE20")
        assert promo.used == 1
    # the code can't be reused by the same user (already redeemed)
    async with SessionFactory() as s:
        user = await s.get(User, 4)
        user.discount_code = "SAVE20"
        await s.commit()
        assert await promos.active_discount(s, user) == 0  # already spent


async def test_consume_keeps_code_when_sale_is_better():
    async with SessionFactory() as s:
        await _code(s, pct=10)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 5)
        await promos.redeem(s, user, "SAVE20")
    async with SessionFactory() as s:
        user = await s.get(User, 5)
        # sale 30% >= promo 10% -> promo not spent, code kept for later
        assert await promos.consume_discount(s, user, sale_pct=30) == 0
        assert user.discount_code == "SAVE20"
        promo = await s.get(PromoCode, "SAVE20")
        assert promo.used == 0


# ---- guards -----------------------------------------------------------------
async def test_expired_discount_not_applied():
    past = datetime.now(UTC) - timedelta(hours=1)
    async with SessionFactory() as s:
        s.add(PromoCode(
            code="OLD", reward_type="discount", reward_amount=20,
            max_uses=5, used=0, is_active=True, expires_at=past,
        ))
        await s.commit()
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 6)
        res = await promos.redeem(s, user, "OLD")
        assert not res.ok and res.status == "invalid"
        assert user.discount_code is None


async def test_new_user_gate_blocks_old_account():
    async with SessionFactory() as s:
        await _code(s, code="NEW10", pct=10, new_user_days=3)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 7)
        user.created_at = datetime.now(UTC) - timedelta(days=10)
        await s.commit()
        res = await promos.redeem(s, user, "NEW10")
        assert not res.ok and res.status == "not_eligible"
        assert user.discount_code is None
