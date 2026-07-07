"""Premium auto-renewal selection + recurring charge (ТЗ §6).

Seeds premium users with/without auto_renew and various sub_expires, then asserts
``due_for_renewal`` selects only opted-in users expiring within the window, that
``attempt_renewal`` returns ``"no_payment_method"`` (without extending) when no token
is saved, and that with a saved method + a successful gateway charge it extends the
subscription and records a renewal transaction.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import select

from core.db import SessionFactory, engine
from core.models import Base, Transaction, User
from core.payments.base import SavedMethod
from core.services import autorenew, payment_methods


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _seed(session, uid, *, auto_renew, expires_in_hours, tier="premium"):
    sub_expires = (
        None
        if expires_in_hours is None
        else datetime.now(UTC) + timedelta(hours=expires_in_hours)
    )
    user = User(
        user_id=uid,
        username=f"u{uid}",
        sub_tier=tier,
        sub_expires=sub_expires,
        auto_renew=auto_renew,
    )
    session.add(user)
    return user


async def test_auto_renew_defaults_false():
    async with SessionFactory() as s:
        await _seed(s, 1, auto_renew=False, expires_in_hours=None, tier=None)
        await s.commit()
        user = await s.get(User, 1)
        assert user.auto_renew is False


async def test_due_selects_only_optin_within_window():
    async with SessionFactory() as s:
        # opted-in, expiring in 10h -> due
        await _seed(s, 1, auto_renew=True, expires_in_hours=10)
        # opted-in but far future -> NOT due
        await _seed(s, 2, auto_renew=True, expires_in_hours=240)
        # expiring soon but NOT opted in -> NOT due
        await _seed(s, 3, auto_renew=False, expires_in_hours=10)
        # opted-in, just lapsed within grace -> due
        await _seed(s, 4, auto_renew=True, expires_in_hours=-2)
        # opted-in, lapsed beyond grace -> NOT due
        await _seed(s, 5, auto_renew=True, expires_in_hours=-200)
        await s.commit()

        due = await autorenew.due_for_renewal(s, within_hours=24)
        assert {u.user_id for u in due} == {1, 4}


async def test_due_respects_within_hours_window():
    async with SessionFactory() as s:
        await _seed(s, 1, auto_renew=True, expires_in_hours=20)
        await s.commit()

        # default 24h window -> included
        assert {u.user_id for u in await autorenew.due_for_renewal(s)} == {1}
        # tighter 12h window -> excluded
        assert await autorenew.due_for_renewal(s, within_hours=12) == []


async def test_attempt_renewal_no_method_does_not_extend():
    async with SessionFactory() as s:
        user = await _seed(s, 1, auto_renew=True, expires_in_hours=5)
        await s.commit()
        original_expires = user.sub_expires

        # No saved payment method -> nothing to charge; sub must NOT be extended.
        result = await autorenew.attempt_renewal(s, user)
        assert result == "no_payment_method"
        assert user.sub_expires == original_expires
        assert user.sub_tier == "premium"


async def test_attempt_renewal_charges_and_extends(monkeypatch):
    async with SessionFactory() as s:
        user = await _seed(s, 1, auto_renew=True, expires_in_hours=5)
        await s.commit()
        original_expires = user.sub_expires
        await payment_methods.save_method(
            s, user_id=1, gateway="yookassa",
            saved=SavedMethod(token="pm_saved_1", last4="4242"),
        )

        # Stub the off-session gateway charge so no network/keys are needed; the
        # service imports charge_saved_method locally, so patching the module attr
        # is picked up at call time.
        seen: dict[str, str] = {}

        async def _fake_charge(method, *, amount, currency, description, payload,
                               idempotency_key=None):
            assert method.token == "pm_saved_1"
            assert payload.startswith("sub:1:premium:1:")
            seen["idem"] = idempotency_key
            return "yk_recurring_tx_1"

        monkeypatch.setattr(
            "core.payments.service.charge_saved_method", _fake_charge
        )

        result = await autorenew.attempt_renewal(s, user)
        assert result == "renewed"
        # The charge carries a deterministic idempotency key tied to the renewed
        # expiry, so a crash-retry before the local commit can't double-charge.
        expected = f"renew:1:{int(autorenew.ensure_aware(original_expires).timestamp())}"
        assert seen["idem"] == expected
        # Subscription extended ~30 days past the prior expiry.
        assert autorenew.ensure_aware(user.sub_expires) > autorenew.ensure_aware(original_expires)
        assert user.sub_tier == "premium"

        # A paid renewal transaction was recorded under the saved method's gateway.
        tx = await s.scalar(select(Transaction).where(Transaction.user_id == 1))
        assert tx is not None
        assert tx.gateway == "yookassa"
        assert tx.gateway_tx_id == "yk_recurring_tx_1"
        assert tx.status == "paid"
        assert tx.duration_months == 1


async def test_attempt_renewal_failed_charge_does_not_extend(monkeypatch):
    from core.payments import PaymentError

    async with SessionFactory() as s:
        user = await _seed(s, 1, auto_renew=True, expires_in_hours=5)
        await s.commit()
        original_expires = user.sub_expires
        await payment_methods.save_method(
            s, user_id=1, gateway="stripe",
            saved=SavedMethod(token="pm_x", customer_id="cus_x"),
        )

        async def _decline(method, **kwargs):
            raise PaymentError("card_declined")

        monkeypatch.setattr("core.payments.service.charge_saved_method", _decline)

        result = await autorenew.attempt_renewal(s, user)
        assert result == "failed"
        assert user.sub_expires == original_expires


async def test_run_autorenew_counts():
    async with SessionFactory() as s:
        await _seed(s, 1, auto_renew=True, expires_in_hours=10)
        await _seed(s, 2, auto_renew=True, expires_in_hours=5)
        await _seed(s, 3, auto_renew=False, expires_in_hours=5)  # not opted in
        await s.commit()

    async with SessionFactory() as s:
        counts = await autorenew.run_autorenew(s)
    # 2 due, none renewed (stub), so 2 skipped
    assert counts == {"due": 2, "renewed": 0, "skipped": 2}


async def test_run_autorenew_opens_own_session():
    async with SessionFactory() as s:
        await _seed(s, 1, auto_renew=True, expires_in_hours=8)
        await s.commit()

    counts = await autorenew.run_autorenew()
    assert counts == {"due": 1, "renewed": 0, "skipped": 1}
