"""Admin payment refund: two-phase state machine (paid → refund_pending →
refunded), real gateway-refund dispatch, and retry of a failed money refund.

Calls the endpoint coroutine directly (FastAPI leaves it callable) with an
explicit session/admin/request, against a real SQLite DB."""
from __future__ import annotations

import types
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException

from api.admin import ops
from core.db import SessionFactory, engine
from core.models import AdminUser, Base, Transaction, User
from core.payments.base import PaymentError
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req():
    # _ip(request) only touches request.client; None → "" (no client host).
    return types.SimpleNamespace(client=None)


async def _admin(session) -> AdminUser:
    a = AdminUser(email="ops@x.io", password_hash=hash_password("x"),
                  role="admin", is_active=True)
    session.add(a)
    await session.commit()
    return a


async def _paid_premium_tx(session, *, gateway: str, uid: int, tx_id: str) -> Transaction:
    session.add(User(
        user_id=uid, language_code="ru", sub_tier="premium",
        sub_expires=datetime.now(UTC) + timedelta(days=60),
    ))
    tx = Transaction(
        user_id=uid, product="premium", duration_months=2, amount=1200,
        currency="rub", gateway=gateway, gateway_tx_id=tx_id, status="paid",
    )
    session.add(tx)
    await session.commit()
    return tx


async def test_failed_gateway_refund_stays_pending_and_retries(monkeypatch):
    async with SessionFactory() as s:
        admin = await _admin(s)
        # stripe is not configured (no key) → money refund fails → refund_pending.
        tx = await _paid_premium_tx(s, gateway="stripe", uid=5001, tx_id="pi_1")

        res = await ops.refund_payment(str(tx.tx_id), _req(), admin=admin, session=s)
        assert res["ok"] is False
        assert res["status"] == "refund_pending"
        assert res["retryable"] is True
        # entitlement revoked immediately even though the money refund didn't land
        assert (await s.get(User, 5001)).is_premium is False

        # retry while the gateway is still unavailable → still pending, no re-revoke
        res2 = await ops.refund_payment(str(tx.tx_id), _req(), admin=admin, session=s)
        assert res2["ok"] is False and res2["status"] == "refund_pending"

        # the gateway becomes able to refund → retry succeeds → refunded
        class _OkProvider:
            def is_available(self) -> bool:
                return True

            async def refund(self, *, gateway_tx_id: str, amount: int) -> str:
                assert gateway_tx_id == "pi_1" and amount == 1200
                return "re_777"

        monkeypatch.setattr(ops, "get_provider", lambda gw: _OkProvider())
        res3 = await ops.refund_payment(str(tx.tx_id), _req(), admin=admin, session=s)
        assert res3["ok"] is True
        assert res3["status"] == "refunded"
        assert res3["gateway_refund"] == "refunded:re_777"

        # a refunded tx is terminal — no double money refund
        with pytest.raises(HTTPException) as ei:
            await ops.refund_payment(str(tx.tx_id), _req(), admin=admin, session=s)
        assert ei.value.status_code == 400


async def test_stars_without_charge_id_refunds_immediately():
    async with SessionFactory() as s:
        admin = await _admin(s)
        session_tx = Transaction(
            user_id=5002, product="credits", qty=100, amount=100, currency="stars",
            gateway="stars", gateway_tx_id=None, status="paid", credits_added=100,
        )
        s.add(User(user_id=5002, language_code="ru", credits=100))
        s.add(session_tx)
        await s.commit()

        res = await ops.refund_payment(str(session_tx.tx_id), _req(), admin=admin, session=s)
        assert res["ok"] is True
        assert res["status"] == "refunded"
        assert res["gateway_refund"] == "skip"
        # credits reversed
        assert (await s.get(User, 5002)).credits == 0


async def test_refund_revokes_entitlement_exactly_once(monkeypatch):
    """A refunded tx is terminal and the entitlement is revoked exactly once, so a
    duplicate refund can neither double-revoke (double-subtracting premium months /
    credits) nor double-refund money. The row lock added to refund_payment extends
    this guarantee to truly-concurrent requests on Postgres; here we assert the
    serialized invariant the lock enforces."""
    calls = {"n": 0}
    real_revoke = ops.revoke_entitlement

    async def _counting_revoke(session, tx):
        calls["n"] += 1
        await real_revoke(session, tx)

    monkeypatch.setattr(ops, "revoke_entitlement", _counting_revoke)

    async with SessionFactory() as s:
        admin = await _admin(s)
        # Stars tx with no charge id → gateway refund is a no-op "skip" → the first
        # call lands on 'refunded' in one shot (no bot/network needed).
        s.add(User(
            user_id=5003, language_code="ru", sub_tier="premium",
            sub_expires=datetime.now(UTC) + timedelta(days=60),
        ))
        tx = Transaction(
            user_id=5003, product="premium", duration_months=2, amount=1200,
            currency="stars", gateway="stars", gateway_tx_id=None, status="paid",
        )
        s.add(tx)
        await s.commit()

        res = await ops.refund_payment(str(tx.tx_id), _req(), admin=admin, session=s)
        assert res["ok"] is True and res["status"] == "refunded"
        assert (await s.get(User, 5003)).is_premium is False
        assert calls["n"] == 1

        # Duplicate refund of the terminal tx is rejected and never revokes again.
        with pytest.raises(HTTPException) as ei:
            await ops.refund_payment(str(tx.tx_id), _req(), admin=admin, session=s)
        assert ei.value.status_code == 400
        assert calls["n"] == 1


async def test_unconfigured_providers_refund_raises_payment_error():
    from core.payments import get_provider

    for gw in ("stripe", "yookassa", "sbp_tribute"):
        with pytest.raises(PaymentError):
            await get_provider(gw).refund(gateway_tx_id="x", amount=100)
