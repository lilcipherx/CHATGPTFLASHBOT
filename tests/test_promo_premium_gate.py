"""Promo Premium reward + new-users-only audience gate (ТЗ §6).

A promo can grant Premium for N days (reward_type='premium', reward_amount=days),
stacking onto an unexpired sub and never downgrading a higher active tier. A promo
with new_user_days > 0 may only be redeemed by accounts younger than that window.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, PromoCode
from core.services import promos
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _make_promo(code: str, **kw) -> None:
    async with SessionFactory() as s:
        s.add(PromoCode(
            code=code,
            reward_type=kw.get("reward_type", "credits"),
            reward_amount=kw.get("reward_amount", 50),
            max_uses=kw.get("max_uses", 100),
            used=0,
            is_active=True,
            new_user_days=kw.get("new_user_days", 0),
        ))
        await s.commit()


async def _set_created_at(uid: int, when: datetime) -> None:
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, uid)
        user.created_at = when
        await s.commit()


async def test_premium_promo_grants_days_and_tier():
    await _make_promo("PREMIUM7", reward_type="premium", reward_amount=7)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 3001)
        res = await promos.redeem(s, user, "PREMIUM7")
        assert res.ok and res.reward_type == "premium" and res.amount == 7
        assert user.sub_tier == "premium"
        assert user.sub_expires is not None
        delta = user.sub_expires - datetime.now(UTC)
        assert timedelta(days=6, hours=23) < delta <= timedelta(days=7)


async def test_premium_promo_stacks_onto_active_sub():
    await _make_promo("EXTEND", reward_type="premium", reward_amount=10)
    base = datetime.now(UTC) + timedelta(days=5)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 3002)
        user.sub_tier = "premium"
        user.sub_expires = base
        await s.commit()
        await promos.redeem(s, user, "EXTEND")
        # 5 remaining days + 10 granted ≈ 15 days out
        delta = user.sub_expires - datetime.now(UTC)
        assert timedelta(days=14, hours=23) < delta <= timedelta(days=15)


async def test_premium_promo_does_not_downgrade_higher_tier():
    await _make_promo("BONUS", reward_type="premium", reward_amount=3)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 3003)
        user.sub_tier = "premium_x2"
        user.sub_expires = datetime.now(UTC) + timedelta(days=2)
        await s.commit()
        await promos.redeem(s, user, "BONUS")
        assert user.sub_tier == "premium_x2"  # not downgraded
        delta = user.sub_expires - datetime.now(UTC)
        assert timedelta(days=4, hours=23) < delta <= timedelta(days=5)


async def test_new_user_gate_allows_fresh_account():
    await _make_promo("NEWBIE", reward_type="credits", reward_amount=20, new_user_days=7)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 3004)  # created_at ≈ now
        res = await promos.redeem(s, user, "NEWBIE")
        assert res.ok and user.credits == 20


async def test_new_user_gate_rejects_old_account():
    await _make_promo("NEWBIE", reward_type="credits", reward_amount=20, new_user_days=7)
    await _set_created_at(3005, datetime.now(UTC) - timedelta(days=30))
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 3005)
        res = await promos.redeem(s, user, "NEWBIE")
        assert not res.ok and res.status == "not_eligible"
    # nothing granted, and the rejected redemption must not consume a use slot
    # (re-read in a fresh session — redeem's rollback expired the objects above).
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 3005)
        assert user.credits == 0
        promo = await s.get(PromoCode, "NEWBIE")
        assert promo.used == 0


async def test_new_user_days_zero_is_open_to_all():
    await _make_promo("OPEN", reward_type="credits", reward_amount=5, new_user_days=0)
    await _set_created_at(3006, datetime.now(UTC) - timedelta(days=365))
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 3006)
        res = await promos.redeem(s, user, "OPEN")
        assert res.ok and user.credits == 5
