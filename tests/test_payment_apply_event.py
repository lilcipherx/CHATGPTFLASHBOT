"""External-gateway webhook application (core.payments.service.apply_event):

* the paid amount is validated against the QUOTE embedded in the payload at
  checkout, so an admin changing a price between checkout and payment can't
  reject a legitimately paid webhook;
* the referral reward is recovered on a DUPLICATE webhook (it runs even when the
  purchase row already existed), closing the crash-between-commits gap.

Real SQLite DB, no network — providers/notifications are not involved here.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, Referral, Transaction, User
from core.payments import PaymentEvent
from core.payments.service import apply_event
from core.services import referrals
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _evt(payload: str, amount: int, tx_id: str = "evt_1") -> PaymentEvent:
    return PaymentEvent(payload=payload, gateway="yookassa",
                        gateway_tx_id=tx_id, amount=amount, status="paid")


async def test_amount_validated_against_embedded_quote(monkeypatch):
    # Checkout embedded the quoted minor amount (84000) in the payload. Even after
    # an admin slashes the live price, the paid webhook for the OLD quote applies.
    async with SessionFactory() as s:
        await get_or_create_user(s, 7001)
        await s.commit()

    # Make the live price table disagree with the quote → would reject if used.
    from core.payments import service as svc
    monkeypatch.setattr(svc, "_expected_minor", lambda *a, **k: 1)

    async with SessionFactory() as s:
        uid = await apply_event(s, _evt("sub:7001:premium:1:84000", amount=84000))
        assert uid == 7001
        assert (await s.get(User, 7001)).is_premium is True


async def test_amount_mismatch_rejected_with_quote():
    # A tampered amount that doesn't match the embedded quote is still rejected.
    async with SessionFactory() as s:
        await get_or_create_user(s, 7002)
        await s.commit()
    async with SessionFactory() as s:
        uid = await apply_event(s, _evt("sub:7002:premium:1:84000", amount=10))
        assert uid is None
        assert (await s.get(User, 7002)).is_premium is False


async def test_legacy_payload_without_quote_falls_back_to_price_table(monkeypatch):
    from core.payments import service as svc
    monkeypatch.setattr(svc, "_expected_minor", lambda *a, **k: 500)
    async with SessionFactory() as s:
        await get_or_create_user(s, 7003)
        await s.commit()
    async with SessionFactory() as s:
        uid = await apply_event(s, _evt("sub:7003:premium:1", amount=500))
        assert uid == 7003


async def test_referral_reward_recovered_on_duplicate_webhook(monkeypatch):
    notified: list[int | None] = []

    # FIX: AUDIT-TEST - match the real notify_referrer signature (it takes reason=);
    # the old mock omitted it → TypeError when service.py calls reason="purchase".
    async def _fake_notify(referrer_id, amount=None, reason=None):
        notified.append(referrer_id)

    monkeypatch.setattr(referrals, "notify_referrer", _fake_notify)

    async with SessionFactory() as s:
        # This test exercises the PAYMENT reward path, so put the program in
        # payment-reward mode (the default is now reward-on-register).
        await referrals.set_settings(s, reward_on_register=False)
        await get_or_create_user(s, 8000)  # referrer
        buyer, _ = await get_or_create_user(s, 8001)
        buyer.referred_by = 8000
        # Simulate the crash window: the purchase committed but the referral row
        # never landed (process died before the reward commit).
        s.add(Transaction(
            user_id=8001, product="premium", duration_months=1, amount=84000,
            currency="rub", gateway="yookassa", gateway_tx_id="evt_dup",
            status="paid",
        ))
        await s.commit()

    # The webhook is REDELIVERED (same gateway_tx_id) → purchase is a duplicate
    # (ok=False), but the referral reward must still be granted now.
    async with SessionFactory() as s:
        uid = await apply_event(
            s, _evt("sub:8001:premium:1:84000", amount=84000, tx_id="evt_dup")
        )
        assert uid is None  # duplicate purchase → no re-notify of the buyer

    async with SessionFactory() as s:
        from sqlalchemy import select
        ref = (await s.scalars(select(Referral))).one()
        assert ref.referrer_id == 8000 and ref.referred_id == 8001
        assert (await s.get(User, 8000)).credits > 0  # referrer was paid
    assert notified == [8000]
