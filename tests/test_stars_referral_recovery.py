"""Stars (native Telegram) payment path recovers a lost referral reward on a
REDELIVERED successful_payment, mirroring the external-gateway apply_event path.

A successful_payment can be redelivered (the bot crashed / the webhook 500'd and
Telegram retried). If the process died between the purchase commit and the
referral-reward commit, the reward is lost; the redelivered event is an
idempotent duplicate of the purchase (no double-grant) but must still grant the
referral reward. Real SQLite DB; the Telegram Message/Bot are stubbed.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest_asyncio
from sqlalchemy import select

from bot.handlers.premium import on_successful_payment
from core.db import SessionFactory, engine
from core.models import Base, Referral, Transaction, User
from core.services import referrals
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


class _Bot:
    def __init__(self):
        self.refunds: list[str] = []

    async def refund_star_payment(self, *, user_id, telegram_payment_charge_id):
        self.refunds.append(telegram_payment_charge_id)


class _Msg:
    def __init__(self, sp):
        self.successful_payment = sp
        self.bot = _Bot()
        self.answered: list[str] = []

    async def answer(self, text):
        self.answered.append(text)


def _sp(payload: str, amount: int, charge_id: str):
    return SimpleNamespace(
        invoice_payload=payload, total_amount=amount,
        telegram_payment_charge_id=charge_id,
    )


async def test_duplicate_stars_payment_recovers_referral_reward(monkeypatch):
    notified: list[int] = []

    async def _fake_notify(referrer_id, amount=None, *, reason=None):
        notified.append(referrer_id)

    monkeypatch.setattr(referrals, "notify_referrer", _fake_notify)

    async with SessionFactory() as s:
        await referrals.set_settings(s, reward_on_register=False)  # payment-reward mode
        await get_or_create_user(s, 9100)  # referrer
        buyer, _ = await get_or_create_user(s, 9101)
        buyer.referred_by = 9100
        # Crash window: the purchase committed, the referral reward never did.
        s.add(Transaction(
            user_id=9101, product="premium", duration_months=1, amount=10,
            currency="stars", gateway="stars", gateway_tx_id="stars_dup",
            status="paid",
        ))
        await s.commit()

    async with SessionFactory() as s:
        buyer = await s.get(User, 9101)
        msg = _Msg(_sp("sub:premium:1", amount=10, charge_id="stars_dup"))
        await on_successful_payment(
            message=msg, state=SimpleNamespace(), session=s, user=buyer,
            _=lambda key, **kw: key,
        )
        # Duplicate purchase → no confirmation message and no refund of a real grant.
        assert msg.answered == []
        assert msg.bot.refunds == []

    async with SessionFactory() as s:
        ref = (await s.scalars(select(Referral))).one()
        assert ref.referrer_id == 9100 and ref.referred_id == 9101
        assert (await s.get(User, 9100)).credits > 0  # referrer was paid
    assert notified == [9100]
