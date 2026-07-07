"""Abandoned-cart tracking + reminder channel (ТЗ §7).

A checkout intent is recorded at the pay step, closed on payment, and an open cart
older than the admin window is nudged once.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from core.db import SessionFactory, engine
from core.models import Base, CheckoutIntent, User
from core.redis_client import redis_client
from core.services import checkout, notify, pricing


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await redis_client.flushall()
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield
    try:
        await pricing.redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


class _FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, user_id, text, **kwargs):
        self.sent.append((user_id, text))


@pytest.fixture
def fake_bot(monkeypatch):
    bot = _FakeBot()
    monkeypatch.setattr("core.bot_client.get_bot", lambda: bot)
    return bot


async def _user(session, uid, **kw):
    session.add(User(user_id=uid, language_code="ru", **kw))
    await session.commit()


# ---- record / refresh -------------------------------------------------------
async def test_record_intent_then_refresh_dedupes():
    async with SessionFactory() as s:
        await _user(s, 1)
        await checkout.record_intent(s, 1, kind="sub", resume_cb="prem:premium",
                                     gateway="stars", amount=600)
        await checkout.record_intent(s, 1, kind="sub", resume_cb="prem:premium",
                                     gateway="yookassa", amount=600)
    async with SessionFactory() as s:
        rows = list(await s.scalars(select(CheckoutIntent)))
        assert len(rows) == 1                 # same cart refreshed, not duplicated
        assert rows[0].gateway == "yookassa"  # latest gateway kept


async def test_mark_completed_closes_open_carts():
    async with SessionFactory() as s:
        await _user(s, 1)
        await checkout.record_intent(s, 1, kind="sub", resume_cb="prem:premium",
                                     gateway="stars", amount=600)
        await checkout.mark_completed(s, 1)
    async with SessionFactory() as s:
        row = await s.scalar(select(CheckoutIntent))
        assert row.completed_at is not None


# ---- abandoned selector -----------------------------------------------------
async def test_abandoned_selects_only_open_old_unreminded_unbanned():
    old = datetime.now(UTC) - timedelta(hours=3)
    fresh = datetime.now(UTC)
    async with SessionFactory() as s:
        await _user(s, 1)                       # open + old -> selected
        await _user(s, 2)                       # open but fresh -> excluded
        await _user(s, 3)                       # completed -> excluded
        await _user(s, 4)                       # already reminded -> excluded
        await _user(s, 5, is_banned=True)       # banned -> excluded
        s.add_all([
            CheckoutIntent(user_id=1, kind="sub", resume_cb="prem:premium",
                           gateway="stars", amount=600, created_at=old),
            CheckoutIntent(user_id=2, kind="sub", resume_cb="prem:premium",
                           gateway="stars", amount=600, created_at=fresh),
            CheckoutIntent(user_id=3, kind="sub", resume_cb="prem:premium",
                           gateway="stars", amount=600, created_at=old,
                           completed_at=fresh),
            CheckoutIntent(user_id=4, kind="sub", resume_cb="prem:premium",
                           gateway="stars", amount=600, created_at=old,
                           reminded_at=fresh),
            CheckoutIntent(user_id=5, kind="sub", resume_cb="prem:premium",
                           gateway="stars", amount=600, created_at=old),
        ])
        await s.commit()
        rows = await checkout.abandoned(s, after_hours=1)
        assert {r.user_id for r in rows} == {1}


# ---- reminder channel -------------------------------------------------------
async def test_run_notifications_abandoned_cart_sends_once(fake_bot):
    old = datetime.now(UTC) - timedelta(hours=2)
    async with SessionFactory() as s:
        await pricing.set_config(s, {"notifications": {
            "premium_expiry_enabled": False, "low_balance_enabled": False,
            "winback_enabled": False, "bonus_available_enabled": False,
            "abandoned_cart_enabled": True, "abandoned_cart_after_hours": 1,
        }})
    async with SessionFactory() as s:
        await _user(s, 1)
        s.add(CheckoutIntent(user_id=1, kind="sub", resume_cb="prem:premium",
                             gateway="stars", amount=600, created_at=old))
        await s.commit()

        first = await notify.run_notifications(s)
        second = await notify.run_notifications(s)

    assert first["abandoned_cart"] == 1
    assert second["abandoned_cart"] == 0          # reminded_at makes it one-shot
    assert {uid for uid, _ in fake_bot.sent} == {1}


# ---- retention --------------------------------------------------------------
async def test_prune_checkout_intents_drops_old_keeps_recent():
    from core.services.retention import prune_checkout_intents

    old = datetime.now(UTC) - timedelta(days=40)
    recent = datetime.now(UTC) - timedelta(days=2)
    async with SessionFactory() as s:
        await _user(s, 1)
        s.add_all([
            CheckoutIntent(user_id=1, kind="sub", resume_cb="prem:premium",
                           gateway="stars", amount=600, created_at=old),
            CheckoutIntent(user_id=1, kind="pack", resume_cb="pack:image_pack",
                           gateway="stars", amount=250, created_at=recent),
        ])
        await s.commit()
        assert await prune_checkout_intents(s, days=30) == 1   # only the 40-day-old row
        remaining = list(await s.scalars(select(CheckoutIntent)))
        assert len(remaining) == 1 and remaining[0].kind == "pack"
