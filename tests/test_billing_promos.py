"""Purchase promos (Loop coverage, money): first-purchase bonus + cashback folded
into a paid top-up, and the one-shot bonus DM accounting. DB + fakeredis.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base
from core.services import billing, pricing
from core.services.credits import get_balance
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    try:
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:
        pass


async def test_first_purchase_bonus_and_cashback_and_notify(monkeypatch):
    import core.bot_client as bot_client

    async def _promos(_session):
        return {"cashback_percent": 10, "first_purchase_bonus": 50, "welcome_bonus": 0}
    monkeypatch.setattr(pricing, "promos", _promos)

    class _FakeBot:
        async def send_message(self, *a, **k):
            return None
    monkeypatch.setattr(bot_client, "get_bot", lambda: _FakeBot())

    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 8001)

        ok = await billing.add_credits(
            s, user, qty=100, gateway="stars", amount=100, gateway_tx_id="tx1"
        )
        assert ok
        # 100 purchased + 10% cashback (10) + first-purchase bonus (50) = 160
        assert await get_balance(s, 8001) == 160

        # notify DMs the bonus (cashback 10 + first 50 = 60); the fake bot succeeds so
        # the one-shot `notified` flag flips.
        assert await billing.notify_purchase_bonus(s, user) == 60
        # one-shot: a second call announces nothing (DM already delivered).
        assert await billing.notify_purchase_bonus(s, user) == 0


async def test_no_promo_when_disabled():
    async with SessionFactory() as s:
        # defaults: first_purchase_bonus=0, cashback_percent=0
        user, _ = await get_or_create_user(s, 8002)
        await billing.add_credits(
            s, user, qty=30, gateway="stars", amount=30, gateway_tx_id="tx2"
        )
        assert await get_balance(s, 8002) == 30  # no bonus applied
        assert await billing.notify_purchase_bonus(s, user) == 0
