"""YooKassa non-webhook paths (Loop coverage): checkout creation, off-session
recurring charge (success / declined / unsettled), and refund. The YooKassa SDK is
monkeypatched (installed, but no network). Webhook verification lives in
test_gateway_webhooks.py.
"""
from __future__ import annotations

import types

import pytest

from core.config import settings
from core.payments.base import CheckoutResult, PaymentError
from core.payments.yookassa_gw import YooKassaProvider


def _ns(**kw):
    return types.SimpleNamespace(**kw)


def _enable(monkeypatch):
    monkeypatch.setattr(settings, "yookassa_shop_id", "shop_1")
    monkeypatch.setattr(settings, "yookassa_secret", "secret_1")
    monkeypatch.setattr(settings, "miniapp_url", "https://app.example")
    # keep the receipt builder inert so the body stays minimal
    monkeypatch.setattr(settings, "yookassa_receipt_enabled", False)


async def test_yookassa_create_checkout(monkeypatch):
    import yookassa
    _enable(monkeypatch)
    captured = {}

    def _create(body, key):
        captured["body"] = body
        return _ns(confirmation=_ns(confirmation_url="https://yookassa/redirect"), id="pay_1")

    monkeypatch.setattr(yookassa.Payment, "create", _create)
    res = await YooKassaProvider().create_checkout(
        amount=10000, currency="RUB", payload="sub:1:pro:1", description="Pro"
    )
    assert isinstance(res, CheckoutResult)
    assert res.url == "https://yookassa/redirect" and res.gateway_tx_id == "pay_1"
    # sub: payloads request a saved method for auto-renewal.
    assert captured["body"].get("save_payment_method") is True


async def test_yookassa_create_checkout_unconfigured_raises(monkeypatch):
    monkeypatch.setattr(settings, "yookassa_shop_id", "")
    monkeypatch.setattr(settings, "yookassa_secret", "")
    with pytest.raises(PaymentError):
        await YooKassaProvider().create_checkout(
            amount=1, currency="RUB", payload="x", description="y"
        )


async def test_yookassa_charge_saved_success_decline_unsettled(monkeypatch):
    import yookassa
    _enable(monkeypatch)

    monkeypatch.setattr(yookassa.Payment, "create",
                        lambda body, key: _ns(status="succeeded", id="pay_ok"))
    pid = await YooKassaProvider().charge_saved(
        token="pm_1", amount=10000, currency="RUB", description="renew",
        payload="sub:1:pro:1", idempotency_key="k1",
    )
    assert pid == "pay_ok"

    def _boom(body, key):
        raise RuntimeError("declined")
    monkeypatch.setattr(yookassa.Payment, "create", _boom)
    with pytest.raises(PaymentError):
        await YooKassaProvider().charge_saved(
            token="pm_1", amount=10000, currency="RUB", description="renew",
            payload="sub:1:pro:1",
        )

    monkeypatch.setattr(yookassa.Payment, "create",
                        lambda body, key: _ns(status="pending", id="pay_p"))
    with pytest.raises(PaymentError):
        await YooKassaProvider().charge_saved(
            token="pm_1", amount=10000, currency="RUB", description="renew",
            payload="sub:1:pro:1",
        )


async def test_yookassa_refund_success(monkeypatch):
    import yookassa
    _enable(monkeypatch)
    monkeypatch.setattr(yookassa.Refund, "create", lambda body, key: _ns(id="ref_1"))
    rid = await YooKassaProvider().refund(gateway_tx_id="pay_1", amount=10000)
    assert rid == "ref_1"
