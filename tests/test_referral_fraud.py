"""Referral anti-fraud age gate (ТЗ §6): withhold a referrer's reward until the
referred account is old enough. Driven by the live ``referral_fraud`` business_config
(default disabled = legacy behaviour). create_all + redis fixture, same as
test_promo_bonuses.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, Referral, User
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


async def _add_user(session, uid: int, *, age_hours: float | None = 0,
                    referred_by: int | None = None) -> User:
    """Insert a User with an explicit created_at (age_hours ago). age_hours=None
    leaves created_at unset (NULL) to exercise the missing-timestamp path."""
    user = User(user_id=uid, referred_by=referred_by)
    if age_hours is not None:
        user.created_at = datetime.now(UTC) - timedelta(hours=age_hours)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# ---- passes_fraud_check unit tests ------------------------------------------
async def test_disabled_passes_regardless_of_age():
    """Default (disabled) -> True even for a brand-new account."""
    async with SessionFactory() as s:
        user = await _add_user(s, 1, age_hours=0)
        assert await referrals.passes_fraud_check(s, user) is True


async def test_enabled_young_account_fails():
    async with SessionFactory() as s:
        await pricing.set_config(
            s, {"referral_fraud": {"enabled": True, "min_referred_age_hours": 24}}
        )
    async with SessionFactory() as s:
        user = await _add_user(s, 2, age_hours=1)  # 1h old < 24h window
        assert await referrals.passes_fraud_check(s, user) is False


async def test_enabled_old_account_passes():
    async with SessionFactory() as s:
        await pricing.set_config(
            s, {"referral_fraud": {"enabled": True, "min_referred_age_hours": 24}}
        )
    async with SessionFactory() as s:
        user = await _add_user(s, 3, age_hours=48)  # 48h old >= 24h window
        assert await referrals.passes_fraud_check(s, user) is True


async def test_enabled_missing_created_at_fails():
    async with SessionFactory() as s:
        await pricing.set_config(
            s, {"referral_fraud": {"enabled": True, "min_referred_age_hours": 24}}
        )
    async with SessionFactory() as s:
        user = await _add_user(s, 4, age_hours=None)  # NULL created_at
        assert await referrals.passes_fraud_check(s, user) is False


# ---- integration: the referrer reward is actually withheld ------------------
async def _referrer_credits(session, referrer_id: int) -> int:
    referrer = await session.get(User, referrer_id)
    return referrer.credits


async def _reward_rows(session) -> int:
    return len((await session.execute(Referral.__table__.select())).all())


async def test_reward_withheld_for_young_referred_on_payment():
    """Feature on + brand-new referred account -> referrer gets NOTHING."""
    async with SessionFactory() as s:
        # payment is the trigger: reward_on_register must be off
        await referrals.set_settings(s, reward_on_register=False)
        await pricing.set_config(
            s, {"referral_fraud": {"enabled": True, "min_referred_age_hours": 24}}
        )
    async with SessionFactory() as s:
        await _add_user(s, 100, age_hours=99)               # the referrer
        referred = await _add_user(s, 101, age_hours=0, referred_by=100)
        result = await referrals.reward_referral_on_payment(s, referred)
        assert result is None                                # withheld
        assert await _referrer_credits(s, 100) == 0
        assert await _reward_rows(s) == 0                    # no Referral row


async def test_reward_granted_for_old_referred_on_payment():
    """Sanity: same path pays out once the referred account is old enough."""
    async with SessionFactory() as s:
        await referrals.set_settings(s, reward_on_register=False)
        await pricing.set_config(
            s, {"referral_fraud": {"enabled": True, "min_referred_age_hours": 24}}
        )
    async with SessionFactory() as s:
        await _add_user(s, 200, age_hours=99)
        referred = await _add_user(s, 201, age_hours=48, referred_by=200)
        result = await referrals.reward_referral_on_payment(s, referred)
        assert result is not None                            # granted
        assert await _referrer_credits(s, 200) > 0
        assert await _reward_rows(s) == 1


async def test_register_reward_not_blocked_by_age_gate():
    """The register reward must NOT be age-gated. It fires at signup (account age
    ~0) and there is no after-aging retry, so applying the age gate here would
    withhold a legitimate reward forever. Register-mode anti-fraud is
    require_subscription / daily_invite_limit; the age gate only guards the PAYMENT
    trigger. Here the age gate is ENABLED and the account is brand-new, yet the
    register reward still pays out."""
    async with SessionFactory() as s:
        # default: reward_on_register=True. Turn the age gate ON (would deny a young
        # account on the payment path) and the subscription gate OFF.
        await referrals.set_settings(s, require_subscription=False)
        await pricing.set_config(
            s, {"referral_fraud": {"enabled": True, "min_referred_age_hours": 24}}
        )
    async with SessionFactory() as s:
        await _add_user(s, 300, age_hours=99)                       # referrer
        referred = await _add_user(s, 301, age_hours=0, referred_by=300)  # brand new
        result = await referrals.reward_referral_on_register(s, None, referred)
        assert result is not None                            # GRANTED despite age gate
        assert await _referrer_credits(s, 300) > 0
        assert await _reward_rows(s) == 1


async def test_register_reward_still_respects_subscription_gate(monkeypatch):
    """Register-mode anti-fraud remains: an unsubscribed user earns nothing when
    require_subscription is on and a gate channel is configured."""
    from core.services import gate

    async def _channels(session):
        return ["@somechannel"]

    async def _not_subbed(bot, user_id, session):
        return False

    monkeypatch.setattr(gate, "active_channels", _channels)
    monkeypatch.setattr(gate, "is_subscribed", _not_subbed)
    async with SessionFactory() as s:
        await _add_user(s, 400, age_hours=99)
        referred = await _add_user(s, 401, age_hours=99, referred_by=400)
        result = await referrals.reward_referral_on_register(s, object(), referred)
        assert result is None                                # withheld pending sub
        assert await _referrer_credits(s, 400) == 0
