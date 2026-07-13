"""Non-webhook gateway paths (Loop L4/L7 coverage): create_checkout / charge_saved /
refund for Stripe, Crypto Pay and Tribute. The webhook signature paths live in
test_gateway_webhooks.py; this hardens the money-OUT and checkout-creation paths that
were previously untested. No network: the Stripe SDK is monkeypatched; httpx is faked.
"""
from __future__ import annotations

import types

import pytest

from core.config import settings
from core.payments.base import CheckoutResult, PaymentError
from core.payments.crypto_gw import CryptoBotProvider
from core.payments.stripe_gw import StripeProvider
from core.payments.tribute_gw import TributeProvider


# --------------------------------------------------------------------------- Stripe
def _ns(**kw):
    return types.SimpleNamespace(**kw)


def _enable_stripe(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret", "sk_test_x")
    monkeypatch.setattr(settings, "miniapp_url", "https://app.example")


async def test_stripe_create_checkout_returns_url_and_id(monkeypatch):
    import stripe
    _enable_stripe(monkeypatch)
    captured = {}

    def _create(**kw):
        captured.update(kw)
        return _ns(url="https://checkout.stripe/x", id="cs_123")

    monkeypatch.setattr(stripe.checkout.Session, "create", _create)
    res = await StripeProvider().create_checkout(
        amount=500, currency="USD", payload="sub:1:pro:1", description="Pro"
    )
    assert isinstance(res, CheckoutResult)
    assert res.url == "https://checkout.stripe/x" and res.gateway_tx_id == "cs_123"
    # sub: payloads must request a reusable off-session method (auto-renewal).
    assert captured["customer_creation"] == "always"
    assert captured["payment_intent_data"] == {"setup_future_usage": "off_session"}
    assert captured["metadata"] == {"payload": "sub:1:pro:1"}


async def test_stripe_create_checkout_unconfigured_raises(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret", "")
    with pytest.raises(PaymentError):
        await StripeProvider().create_checkout(
            amount=1, currency="USD", payload="credits:1:10", description="x"
        )


async def test_stripe_charge_saved_success_and_decline(monkeypatch):
    import stripe
    _enable_stripe(monkeypatch)

    monkeypatch.setattr(stripe.PaymentIntent, "create",
                        lambda **kw: _ns(status="succeeded", id="pi_ok"))
    pid = await StripeProvider().charge_saved(
        token="pm_1", customer_id="cus_1", amount=500, currency="USD",
        description="renew", payload="sub:1:pro:1", idempotency_key="k1",
    )
    assert pid == "pi_ok"

    # A declined off-session charge raises PaymentError (can't prompt for auth).
    def _boom(**kw):
        raise RuntimeError("card_declined")
    monkeypatch.setattr(stripe.PaymentIntent, "create", _boom)
    with pytest.raises(PaymentError):
        await StripeProvider().charge_saved(
            token="pm_1", customer_id="cus_1", amount=500, currency="USD",
            description="renew", payload="sub:1:pro:1",
        )

    # A non-succeeded status is also a failure (money not settled).
    monkeypatch.setattr(stripe.PaymentIntent, "create",
                        lambda **kw: _ns(status="requires_action", id="pi_x"))
    with pytest.raises(PaymentError):
        await StripeProvider().charge_saved(
            token="pm_1", customer_id="cus_1", amount=500, currency="USD",
            description="renew", payload="sub:1:pro:1",
        )


async def test_stripe_refund_success_and_missing_intent(monkeypatch):
    import stripe
    _enable_stripe(monkeypatch)

    monkeypatch.setattr(stripe.checkout.Session, "retrieve",
                        lambda sid: _ns(payment_intent="pi_1"))
    monkeypatch.setattr(stripe.Refund, "create", lambda **kw: _ns(id="re_1"))
    rid = await StripeProvider().refund(gateway_tx_id="cs_1", amount=500)
    assert rid == "re_1"

    # A session with no payment_intent → PaymentError (nothing to refund).
    monkeypatch.setattr(stripe.checkout.Session, "retrieve",
                        lambda sid: _ns(payment_intent=None))
    with pytest.raises(PaymentError):
        await StripeProvider().refund(gateway_tx_id="cs_1", amount=500)


async def test_stripe_verify_webhook_paid_captures_saved_method(monkeypatch):
    import stripe
    monkeypatch.setattr(settings, "stripe_secret", "sk_test_x")
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")
    event = {"type": "checkout.session.completed", "data": {"object": {
        "id": "cs_1", "payment_status": "paid", "amount_total": 500,
        "metadata": {"payload": "sub:1:premium:1"},
        "customer": "cus_1", "payment_intent": "pi_1",
    }}}
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda b, s, secret: event)
    monkeypatch.setattr(stripe.PaymentIntent, "retrieve", lambda pid: _ns(payment_method="pm_1"))
    ev = StripeProvider().verify_webhook({"stripe-signature": "t=1,v1=x"}, b"{}")
    assert ev is not None and ev.gateway_tx_id == "cs_1" and ev.amount == 500
    # a sub checkout captures the vaulted method for auto-renewal
    assert ev.saved_method is not None and ev.saved_method.token == "pm_1"


def test_stripe_verify_webhook_unpaid_is_none(monkeypatch):
    import stripe
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")
    event = {"type": "checkout.session.completed",
             "data": {"object": {"payment_status": "unpaid"}}}
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda b, s, secret: event)
    # `completed` before funds clear → not activated
    assert StripeProvider().verify_webhook({"stripe-signature": "x"}, b"{}") is None


# ---------------------------------------------------------------------- fake httpx
class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Minimal async-context httpx.AsyncClient stand-in returning a canned payload."""
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kw):
        self.calls.append((url, kw))
        return _FakeResp(self._payload)


def _patch_httpx(monkeypatch, payload):
    import httpx
    client = _FakeClient(payload)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: client)
    return client


# ----------------------------------------------------------------------- Crypto Pay
async def test_crypto_create_checkout_success(monkeypatch):
    monkeypatch.setattr(settings, "crypto_pay_token", "tok")
    _patch_httpx(monkeypatch, {"ok": True, "result": {
        "invoice_id": 77, "bot_invoice_url": "https://t.me/CryptoBot?start=x"}})
    res = await CryptoBotProvider().create_checkout(
        amount=1234, currency="USD", payload="pack:1:img:5", description="Pack"
    )
    assert res.url == "https://t.me/CryptoBot?start=x" and res.gateway_tx_id == "77"


async def test_crypto_create_checkout_api_error_raises(monkeypatch):
    monkeypatch.setattr(settings, "crypto_pay_token", "tok")
    _patch_httpx(monkeypatch, {"ok": False, "error": "bad"})
    with pytest.raises(PaymentError):
        await CryptoBotProvider().create_checkout(
            amount=100, currency="USD", payload="credits:1:10", description="x"
        )


async def test_crypto_create_checkout_unconfigured_and_refund(monkeypatch):
    monkeypatch.setattr(settings, "crypto_pay_token", "")
    with pytest.raises(PaymentError):
        await CryptoBotProvider().create_checkout(
            amount=100, currency="USD", payload="x", description="x"
        )
    # Crypto Pay has no programmatic refund — must raise so the caller keeps it pending.
    with pytest.raises(PaymentError):
        await CryptoBotProvider().refund(gateway_tx_id="77", amount=100)


# -------------------------------------------------------------------------- Tribute
async def test_tribute_checkout_inert_until_verified(monkeypatch):
    monkeypatch.setattr(settings, "tribute_api_key", "k")
    monkeypatch.setattr(settings, "tribute_api_verified", False)
    with pytest.raises(PaymentError):
        await TributeProvider().create_checkout(
            amount=1000, currency="RUB", payload="sub:1:pro:1", description="Pro"
        )


async def test_tribute_checkout_success_when_verified(monkeypatch):
    monkeypatch.setattr(settings, "tribute_api_key", "k")
    monkeypatch.setattr(settings, "tribute_api_verified", True)
    _patch_httpx(monkeypatch, {"payment_url": "https://tribute.tg/pay/9", "id": 9})
    res = await TributeProvider().create_checkout(
        amount=1000, currency="RUB", payload="sub:1:pro:1", description="Pro"
    )
    assert res.url == "https://tribute.tg/pay/9" and res.gateway_tx_id == "9"
    # Refund is manual for the unverified integration.
    with pytest.raises(PaymentError):
        await TributeProvider().refund(gateway_tx_id="9", amount=1000)
