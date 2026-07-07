"""Promo bonus mechanics (ТЗ §4): welcome bonus, first-purchase bonus, cashback %.

All driven by live business_config (default 0 = off). Billing functions are called
directly against a real SQLite DB (same pattern as test_business_admin).
"""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, User
from core.services import billing, pricing
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


async def _user(session, uid=1) -> User:
    # Use the real signup path so a PackBalance row exists (as in production).
    u, _ = await get_or_create_user(session, uid, username="u")
    return u


async def test_promos_defaults_off():
    async with SessionFactory() as s:
        p = await pricing.promos(s)
        assert p == {"welcome_bonus": 0, "first_purchase_bonus": 0, "cashback_percent": 0}


async def test_welcome_bonus_on_new_user():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"promos": {"welcome_bonus": 30}})
    async with SessionFactory() as s:
        user, created = await get_or_create_user(s, 555, username="new")
        assert created is True
        assert user.credits == 30
    # a returning user is NOT re-granted
    async with SessionFactory() as s:
        user, created = await get_or_create_user(s, 555, username="new")
        assert created is False
        assert user.credits == 30


async def test_no_welcome_bonus_by_default():
    async with SessionFactory() as s:
        user, created = await get_or_create_user(s, 777)
        assert created is True and user.credits == 0


async def test_cashback_on_credit_topup():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"promos": {"cashback_percent": 10}})
    async with SessionFactory() as s:
        user = await _user(s)
        ok = await billing.add_credits(
            s, user, qty=100, gateway="stars", amount=100, gateway_tx_id="t1"
        )
        assert ok is True
        await s.refresh(user)
        # 100 purchased + 10% cashback = 110
        assert user.credits == 110


async def test_first_purchase_bonus_once():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"promos": {"first_purchase_bonus": 50}})
    async with SessionFactory() as s:
        user = await _user(s)
        await billing.activate_subscription(
            s, user, product="premium", months=1, gateway="stars",
            amount=100, gateway_tx_id="sub1",
        )
        await s.refresh(user)
        assert user.credits == 50  # first purchase -> bonus

        # a second purchase does NOT grant the first-purchase bonus again
        await billing.add_pack_credits(
            s, user, pack="image_pack", qty=50, gateway="stars",
            amount=200, gateway_tx_id="pack1",
        )
        await s.refresh(user)
        assert user.credits == 50  # unchanged (no cashback on packs)


async def test_first_purchase_and_cashback_stack_on_credits():
    async with SessionFactory() as s:
        await pricing.set_config(
            s, {"promos": {"first_purchase_bonus": 20, "cashback_percent": 10}}
        )
    async with SessionFactory() as s:
        user = await _user(s)
        await billing.add_credits(
            s, user, qty=100, gateway="stars", amount=100, gateway_tx_id="c1"
        )
        await s.refresh(user)
        # 100 purchased + 10 cashback + 20 first-purchase = 130
        assert user.credits == 130


async def test_duplicate_webhook_grants_no_promo():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"promos": {"cashback_percent": 50}})
    async with SessionFactory() as s:
        user = await _user(s)
        await billing.add_credits(
            s, user, qty=100, gateway="stars", amount=100, gateway_tx_id="dup"
        )
        await s.refresh(user)
        assert user.credits == 150  # 100 + 50% once
        # replay the same charge id -> idempotent, no extra credits/cashback
        ok = await billing.add_credits(
            s, user, qty=100, gateway="stars", amount=100, gateway_tx_id="dup"
        )
        assert ok is False
        await s.refresh(user)
        assert user.credits == 150


# ---- bonus visibility (purchase-bonus DM) -----------------------------------
async def test_notify_purchase_bonus_once(monkeypatch):
    # The one-shot guard only flips `notified` AFTER the DM sends, so stub the bot
    # (no Telegram in tests) — otherwise the send raises, notified stays False, and
    # both calls would re-announce. This mirrors production where the DM succeeds.
    class _FakeBot:
        async def send_message(self, *a, **k):
            return None

    monkeypatch.setattr("core.bot_client.get_bot", lambda: _FakeBot())

    async with SessionFactory() as s:
        await pricing.set_config(s, {"promos": {"cashback_percent": 10}})
    async with SessionFactory() as s:
        user = await _user(s)
        await billing.add_credits(
            s, user, qty=100, gateway="stars", amount=100, gateway_tx_id="b1"
        )
        # first call announces the 10 ✨ cashback; second is a no-op (one-shot guard)
        assert await billing.notify_purchase_bonus(s, user) == 10
        assert await billing.notify_purchase_bonus(s, user) == 0


async def test_notify_purchase_bonus_noop_without_bonus():
    async with SessionFactory() as s:
        user = await _user(s)  # no promos configured
        await billing.add_credits(
            s, user, qty=100, gateway="stars", amount=100, gateway_tx_id="nb"
        )
        assert await billing.notify_purchase_bonus(s, user) == 0
