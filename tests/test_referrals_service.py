"""Referral settings + attribution helpers (Loop coverage): milestone normalisation,
settings round-trip, invite counting + daily-limit gating, the default-open fraud age
gate, and the idempotent two-sided invitee welcome grant. DB only, no network.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base
from core.services import referrals
from core.services.credits import get_balance
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def test_clean_milestones_normalises_and_drops_invalid():
    # string keys/values tolerated; non-positive + non-numeric dropped; non-dict → {}.
    assert referrals._clean_milestones({"3": "10", "5": 20}) == {3: 10, 5: 20}
    assert referrals._clean_milestones({"0": 5, "2": 0, "x": "y"}) == {}
    assert referrals._clean_milestones(None) == {}


async def test_settings_round_trip_and_defaults():
    async with SessionFactory() as s:
        out = await referrals.set_settings(
            s, enabled=True, reward_credits=15, daily_invite_limit=3,
            invitee_reward_credits=5,
        )
        assert out["enabled"] is True and out["reward_credits"] == 15
        assert out["daily_invite_limit"] == 3 and out["invitee_reward_credits"] == 5
        # read-back applies the same coercions
        again = await referrals.get_settings(s)
        assert again["reward_credits"] == 15


async def test_count_and_can_attribute_invite():
    async with SessionFactory() as s:
        await referrals.set_settings(s, enabled=True, daily_invite_limit=2)
        for uid in (7001, 7002):
            u, _ = await get_or_create_user(s, uid)
            u.referred_by = 9000
        await s.commit()

        assert await referrals.count_referrals(s, 9000) == 2
        # 2 invited today, limit 2 → no more attributions allowed.
        assert await referrals.can_attribute_invite(s, 9000) is False
        # a referrer with none used is still under the limit
        assert await referrals.can_attribute_invite(s, 9999) is True
        # disabled program → never attribute
        await referrals.set_settings(s, enabled=False)
        assert await referrals.can_attribute_invite(s, 9999) is False


async def test_fraud_check_default_open():
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 7100)
        # referral_fraud business_config defaults to disabled → gate is open.
        assert await referrals.passes_fraud_check(s, user) is True


async def test_invitee_welcome_grants_once():
    async with SessionFactory() as s:
        await referrals.set_settings(s, enabled=True, invitee_reward_credits=5)
        invited, _ = await get_or_create_user(s, 7200)
        invited.referred_by = 8000
        await s.commit()

        granted = await referrals.grant_invitee_welcome(s, invited)
        assert granted == 5
        assert await get_balance(s, 7200) == 5
        # Idempotent: a second attribution grants nothing more.
        assert await referrals.grant_invitee_welcome(s, invited) == 0

        # A user with no referrer gets nothing.
        solo, _ = await get_or_create_user(s, 7201)
        assert await referrals.grant_invitee_welcome(s, solo) == 0
