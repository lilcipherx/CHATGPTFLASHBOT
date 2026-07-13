"""apply_event happy path (Loop coverage, money): a verified paid credits event flows
through the whole post-apply chain — grant, referral reward, loyalty tier, purchase-
bonus notify, discount spend, cart close — for a real user. Best-effort notifications
are stubbed so nothing hits the network.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base
from core.payments.base import PaymentEvent
from core.payments.service import apply_event
from core.services.credits import get_balance
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_apply_event_credits_applies_and_runs_hooks(monkeypatch):
    import core.bot_client as bc

    class _FakeBot:
        async def send_message(self, *a, **k):
            return None
    monkeypatch.setattr(bc, "get_bot", lambda: _FakeBot())

    async with SessionFactory() as s:
        await get_or_create_user(s, 6100)
        # quoted-minor payload form: credits base = 3 fields + trailing quoted minor.
        # amount matches the quote → passes the tamper guard → applies.
        minor = 500
        ev = PaymentEvent(payload=f"credits:6100:10:{minor}", gateway="stripe",
                          gateway_tx_id="cx1", amount=minor, status="paid")
        uid = await apply_event(s, ev)
        assert uid == 6100
        assert await get_balance(s, 6100) == 10

        # a duplicate delivery of the same charge is a no-op (idempotent) → None
        dup = await apply_event(s, ev)
        assert dup is None


async def test_apply_event_sub_and_avatar(monkeypatch):
    import core.bot_client as bc

    class _FakeBot:
        async def send_message(self, *a, **k):
            return None
    monkeypatch.setattr(bc, "get_bot", lambda: _FakeBot())

    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 6200)
        # subscription: base=4 fields + quoted minor; premium 1 month
        sub = PaymentEvent(payload="sub:6200:premium:1:900", gateway="stripe",
                           gateway_tx_id="sx1", amount=900, status="paid")
        assert await apply_event(s, sub) == 6200
        await s.refresh(user)
        assert user.sub_expires is not None

        # avatar one-time: base=2 fields + quoted minor
        av = PaymentEvent(payload="avatar:6200:700", gateway="stripe",
                          gateway_tx_id="ax1", amount=700, status="paid")
        assert await apply_event(s, av) == 6200


async def test_apply_event_amount_mismatch_rejected():
    async with SessionFactory() as s:
        await get_or_create_user(s, 6101)
        # quoted minor says 500 but the "paid" amount is 999 → tamper guard rejects.
        ev = PaymentEvent(payload="credits:6101:10:500", gateway="stripe",
                          gateway_tx_id="cx2", amount=999, status="paid")
        assert await apply_event(s, ev) is None
        assert await get_balance(s, 6101) == 0


async def test_apply_event_ignores_unpaid_and_empty():
    async with SessionFactory() as s:
        assert await apply_event(s, PaymentEvent(
            payload="credits:1:10:500", gateway="stripe", gateway_tx_id="x",
            amount=500, status="pending")) is None
        assert await apply_event(s, PaymentEvent(
            payload="", gateway="stripe", gateway_tx_id="x", amount=0,
            status="paid")) is None
