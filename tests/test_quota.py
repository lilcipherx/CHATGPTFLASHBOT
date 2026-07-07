"""Quota math (limits now read the live business-config) + catalog integrity.

The limit functions are async + DB-backed (limits come from core.services.pricing,
which falls back to the .env/code defaults when no admin override is set). A clean
schema per test ensures no leftover override row from another test file leaks in.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from core.constants import (
    FREE_MODEL_KEYS,
    PACK_PRICES,
    SUBSCRIPTION_PRICES,
    TEXT_MODELS,
)
from core.db import SessionFactory, engine
from core.models import Base, User
from core.services import pricing, quota


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


def _user(**kw) -> User:
    u = User(user_id=1, language_code="ru")
    for k, v in kw.items():
        setattr(u, k, v)
    return u


async def test_free_user_weekly_limit():
    u = _user(text_req_week=100, week_start=datetime.now(UTC))
    async with SessionFactory() as s:
        state = await quota.text_quota_state(s, u)
    assert state.allowed is False
    assert state.limit == 100
    assert state.is_premium is False


async def test_weekly_reset_after_7_days():
    u = _user(text_req_week=100, week_start=datetime.now(UTC) - timedelta(days=8))
    async with SessionFactory() as s:
        state = await quota.text_quota_state(s, u)
    assert state.used == 0
    assert state.allowed is True


async def test_premium_uses_daily_limit():
    u = _user(
        sub_tier="premium_x2",
        sub_expires=datetime.now(UTC) + timedelta(days=10),
        text_req_day=0,
        day_start=datetime.now(UTC),
    )
    async with SessionFactory() as s:
        state = await quota.text_quota_state(s, u)
    assert state.is_premium is True
    assert state.limit == 200


async def test_admin_override_changes_limit_live():
    # An admin lowering the free weekly limit applies immediately.
    async with SessionFactory() as s:
        await pricing.set_config(s, {"limits": {"free_text_weekly": 5}})
    u = _user(text_req_week=5, week_start=datetime.now(UTC))
    async with SessionFactory() as s:
        state = await quota.text_quota_state(s, u)
    assert state.limit == 5
    assert state.allowed is False


async def test_naive_datetime_does_not_crash():
    # SQLite returns timezone-naive datetimes; quota math must not raise.
    naive_old = datetime.now() - timedelta(days=8)  # naive, >1 week ago
    u = _user(text_req_week=50, week_start=naive_old)
    async with SessionFactory() as s:
        state = await quota.text_quota_state(s, u)  # must not raise
    assert state.used == 0  # weekly window elapsed -> reset


async def test_naive_sub_expires_is_premium():
    naive_future = datetime.now() + timedelta(days=5)  # naive
    u = _user(sub_tier="premium", sub_expires=naive_future)
    assert u.is_premium is True  # must not raise on naive comparison


async def _add_user(s, **kw) -> User:
    u = _user(**kw)
    s.add(u)
    await s.commit()
    return u


async def test_base_quota_spent_before_credits():
    # While the weekly allowance has room, ✨ is untouched.
    async with SessionFactory() as s:
        u = await _add_user(s, text_req_week=0, week_start=datetime.now(UTC), credits=5)
        st = await quota.consume_text(s, u, cost=1)
    assert st.allowed is True
    assert st.credits_charged == 0
    assert u.text_req_week == 1
    assert u.credits == 5  # untouched while base remains


async def test_credits_pay_when_weekly_exhausted():
    # Base weekly limit (100) is full → the request is paid from the ✨ balance.
    async with SessionFactory() as s:
        u = await _add_user(s, text_req_week=100, week_start=datetime.now(UTC), credits=5)
        st = await quota.consume_text(s, u, cost=1)
    assert st.allowed is True
    assert st.credits_charged == 1
    assert st.credits_balance == 4
    assert u.credits == 4
    assert u.text_req_week == 100  # base counter not pushed past its limit


async def test_refund_after_credit_charge_returns_to_credits():
    async with SessionFactory() as s:
        u = await _add_user(s, text_req_week=100, week_start=datetime.now(UTC), credits=5)
        st = await quota.consume_text(s, u, cost=1)
        assert u.credits == 4
        await quota.refund_text(s, u, 1, credits_charged=st.credits_charged)
    assert u.credits == 5            # ✨ given back
    assert u.text_req_week == 100    # quota counter untouched by the refund


async def test_quota_exceeded_only_when_base_and_credits_empty():
    async with SessionFactory() as s:
        u = await _add_user(s, text_req_week=100, week_start=datetime.now(UTC), credits=0)
        with pytest.raises(quota.QuotaExceeded):
            await quota.consume_text(s, u, cost=1)


async def test_multicredit_cost_paid_whole_from_credits():
    # A 3-credit request that won't fit the base remainder is paid entirely from ✨
    # (whole-to-one-budget rule keeps refunds unambiguous).
    async with SessionFactory() as s:
        u = await _add_user(s, text_req_week=99, week_start=datetime.now(UTC), credits=5)
        st = await quota.consume_text(s, u, cost=3)
    assert st.credits_charged == 3
    assert u.credits == 2
    assert u.text_req_week == 99  # base remainder left intact, not split


async def test_pricing_catalog_complete():
    assert SUBSCRIPTION_PRICES["premium"][12] == 3000
    assert SUBSCRIPTION_PRICES["premium_x2"][1] == 900
    assert PACK_PRICES["image_pack"][500] == 1750
    assert {"gpt_5_mini", "deepseek_v4", "gemini_3_1_flash"} <= FREE_MODEL_KEYS
    assert len(TEXT_MODELS) == 9
