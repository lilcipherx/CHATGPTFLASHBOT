"""Admin referral settings — GET and PUT must return the SAME shape.

Regression: the page applies the PUT response body directly, so a PUT that omitted
`stats` crashed the render on save (s.stats.top_referrers threw). Calls the endpoint
coroutines directly against a real SQLite DB.
"""
from __future__ import annotations

import types

import pytest_asyncio

from api.admin import ops
from core.db import SessionFactory, engine
from core.models import AdminUser, Base
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req():
    return types.SimpleNamespace(client=None)


async def _admin(session) -> AdminUser:
    a = AdminUser(email="r@x.io", password_hash=hash_password("x"), role="admin", is_active=True)
    session.add(a)
    await session.commit()
    return a


async def test_put_returns_stats_block_like_get():
    async with SessionFactory() as s:
        a = await _admin(s)
        get_out = await ops.referral_settings(admin=a, session=s)
        put_out = await ops.set_referral_settings(
            ops.ReferralSettingsReq(reward_credits=15), _req(), admin=a, session=s
        )

    # The save handler does apply(put_out); a missing stats block white-screens the page.
    assert "stats" in put_out, "PUT must return the stats block GET returns"
    assert "top_referrers" in put_out["stats"]
    assert put_out["stats"]["top_referrers"] == []  # no referrals seeded
    assert put_out["reward_credits"] == 15
    # Same top-level keys in both responses.
    assert set(get_out) == set(put_out)


async def test_age_fraud_settings_merged_in_and_persisted():
    """The account-age anti-fraud (referral_fraud) is editable through the SAME
    referral-settings endpoint, so the whole program lives on one page."""
    async with SessionFactory() as s:
        a = await _admin(s)
        out = await ops.set_referral_settings(
            ops.ReferralSettingsReq(age_fraud_enabled=True, min_referred_age_hours=48),
            _req(), admin=a, session=s,
        )
        assert out["age_fraud_enabled"] is True
        assert out["min_referred_age_hours"] == 48
        # persisted: a fresh GET reflects it
        again = await ops.referral_settings(admin=a, session=s)
        assert again["age_fraud_enabled"] is True
        assert again["min_referred_age_hours"] == 48
        # partial update keeps the other field (deep-merge)
        out2 = await ops.set_referral_settings(
            ops.ReferralSettingsReq(age_fraud_enabled=False), _req(), admin=a, session=s,
        )
        assert out2["age_fraud_enabled"] is False
        assert out2["min_referred_age_hours"] == 48
