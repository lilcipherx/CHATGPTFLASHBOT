"""Two-sided referrals + milestone bonuses + total-earned (ТЗ §6).

A referral can now reward BOTH sides (a welcome ✨ to the invited user), grant the
referrer a one-time milestone bonus when their invite-count crosses an admin
threshold, and report the referrer's lifetime earnings. All idempotent.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, User
from core.services import pricing, referrals


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


async def _seed(referrer: int, invitees: list[int]) -> None:
    async with SessionFactory() as s:
        s.add(User(user_id=referrer, language_code="ru", credits=0))
        for uid in invitees:
            s.add(User(user_id=uid, language_code="ru", credits=0, referred_by=referrer))
        await s.commit()


# ---- invitee welcome bonus --------------------------------------------------
async def test_invitee_welcome_granted_once():
    await _seed(100, [300])
    async with SessionFactory() as s:
        await referrals.set_settings(s, invitee_reward_credits=25)
    async with SessionFactory() as s:
        invitee = await s.get(User, 300)
        assert await referrals.grant_invitee_welcome(s, invitee) == 25
    async with SessionFactory() as s:
        invitee = await s.get(User, 300)
        assert invitee.credits == 25
        assert await referrals.grant_invitee_welcome(s, invitee) == 0   # idempotent
        assert invitee.credits == 25


async def test_invitee_welcome_off_by_default():
    await _seed(100, [301])
    async with SessionFactory() as s:
        invitee = await s.get(User, 301)
        assert await referrals.grant_invitee_welcome(s, invitee) == 0
        assert invitee.credits == 0


# ---- milestone bonuses + total earned ---------------------------------------
async def test_milestone_bonus_and_total_earned():
    await _seed(100, [201, 202, 203])
    async with SessionFactory() as s:
        await referrals.set_settings(
            s, reward_on_register=False, reward_credits=10, milestones={"3": 100},
        )
    # Reward the referrer for each invitee's first payment (payment-trigger mode).
    for uid in (201, 202, 203):
        async with SessionFactory() as s:
            invitee = await s.get(User, uid)
            assert await referrals.reward_referral_on_payment(s, invitee) is not None

    async with SessionFactory() as s:
        referrer = await s.get(User, 100)
        # 3 × 10 per-invite + a single 100 milestone for crossing 3 invites
        assert referrer.credits == 130
        assert await referrals.total_earned(s, 100) == 130


async def test_no_milestones_configured_grants_only_per_invite():
    await _seed(100, [210, 211])
    async with SessionFactory() as s:
        await referrals.set_settings(s, reward_on_register=False, reward_credits=10, milestones={})
    for uid in (210, 211):
        async with SessionFactory() as s:
            invitee = await s.get(User, uid)
            await referrals.reward_referral_on_payment(s, invitee)
    async with SessionFactory() as s:
        referrer = await s.get(User, 100)
        assert referrer.credits == 20
        assert await referrals.total_earned(s, 100) == 20
