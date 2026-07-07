"""Per-gateway ``verify_webhook`` signature/authenticity checks (the money entry
point). Covers: a valid signed paid event → PaymentEvent; a forged/missing
signature → PaymentError; an unconfigured gateway refusing to verify; non-paid
events → None; and YooKassa's invariant that the (unsigned) body is never trusted —
amount/status/payload come from the authenticated server re-fetch.

No network: the Stripe/YooKassa SDK calls are monkeypatched; Crypto/Tribute HMAC is
computed locally with the same scheme the verifier uses."""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from core.config import settings
from core.payments.base import PaymentError, PaymentRetryable, gateway_currency
from core.payments.crypto_gw import CryptoBotProvider
from core.payments.stripe_gw import StripeProvider
from core.payments.tribute_gw import TributeProvider
from core.payments.yookassa_gw import YooKassaProvider


# --- Crypto Pay (@CryptoBot): secret = SHA256(token), HMAC-SHA256 over body --------
def test_gateway_currency_mapping():
    # USD gateways, RUB gateways, and Stars — the ledger must label the unit
    # correctly (Stripe/Crypto are USD, YooKassa/СБП are RUB).
    assert gateway_currency("stripe") == "usd"
    assert gateway_currency("crypto") == "usd"
    assert gateway_currency("yookassa") == "rub"
    assert gateway_currency("sbp_tribute") == "rub"
    assert gateway_currency("stars") == "stars"
    assert gateway_currency("gift") == "rub"  # 0-amount gifts fall to the rub default


def _crypto_sig(token: str, body: bytes) -> str:
    secret = hashlib.sha256(token.encode()).digest()
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def test_crypto_unconfigured_refuses(monkeypatch):
    monkeypatch.setattr(settings, "crypto_pay_token", "")
    with pytest.raises(PaymentError):
        CryptoBotProvider().verify_webhook({"crypto-pay-api-signature": "x"}, b"{}")


def test_crypto_valid_signature_paid(monkeypatch):
    monkeypatch.setattr(settings, "crypto_pay_token", "tok")
    body = json.dumps({
        "update_type": "invoice_paid",
        "payload": {"status": "paid", "amount": "5.00", "invoice_id": 42,
                    "payload": "buy:credits_100"},
    }).encode()
    ev = CryptoBotProvider().verify_webhook(
        {"crypto-pay-api-signature": _crypto_sig("tok", body)}, body
    )
    assert ev is not None
    assert ev.gateway == "crypto" and ev.gateway_tx_id == "42"
    assert ev.amount == 500 and ev.payload == "buy:credits_100" and ev.status == "paid"


def test_crypto_forged_signature_raises(monkeypatch):
    monkeypatch.setattr(settings, "crypto_pay_token", "tok")
    body = b'{"update_type":"invoice_paid"}'
    with pytest.raises(PaymentError):
        CryptoBotProvider().verify_webhook({"crypto-pay-api-signature": "deadbeef"}, body)


def test_crypto_missing_signature_raises(monkeypatch):
    monkeypatch.setattr(settings, "crypto_pay_token", "tok")
    with pytest.raises(PaymentError):
        CryptoBotProvider().verify_webhook({}, b"{}")


def test_crypto_valid_signature_non_paid_update_is_none(monkeypatch):
    monkeypatch.setattr(settings, "crypto_pay_token", "tok")
    body = json.dumps({"update_type": "invoice_created"}).encode()
    out = CryptoBotProvider().verify_webhook(
        {"crypto-pay-api-signature": _crypto_sig("tok", body)}, body
    )
    assert out is None


# --- Tribute (СБП): inert until verified; HMAC-SHA256(key, body) -------------------
def test_tribute_inert_until_verified(monkeypatch):
    monkeypatch.setattr(settings, "tribute_api_key", "k")
    monkeypatch.setattr(settings, "tribute_api_verified", False)
    # A valid-looking paid body is still ignored (returns None) while unverified.
    assert TributeProvider().verify_webhook({}, b'{"status":"paid"}') is None


def test_tribute_valid_signature_paid(monkeypatch):
    monkeypatch.setattr(settings, "tribute_api_key", "k")
    monkeypatch.setattr(settings, "tribute_api_verified", True)
    body = json.dumps({"status": "paid", "id": 7, "amount": 50000,
                       "metadata": {"payload": "sub:premium:1"}}).encode()
    sig = hmac.new(b"k", body, hashlib.sha256).hexdigest()
    ev = TributeProvider().verify_webhook({"x-tribute-signature": sig}, body)
    assert ev is not None
    assert ev.gateway == "sbp_tribute" and ev.gateway_tx_id == "7"
    assert ev.amount == 50000 and ev.payload == "sub:premium:1"


def test_tribute_forged_signature_raises(monkeypatch):
    monkeypatch.setattr(settings, "tribute_api_key", "k")
    monkeypatch.setattr(settings, "tribute_api_verified", True)
    with pytest.raises(PaymentError):
        TributeProvider().verify_webhook({"x-tribute-signature": "bad"}, b'{"status":"paid"}')


def test_tribute_valid_signature_unknown_status_is_none(monkeypatch):
    monkeypatch.setattr(settings, "tribute_api_key", "k")
    monkeypatch.setattr(settings, "tribute_api_verified", True)
    body = json.dumps({"status": "pending"}).encode()
    sig = hmac.new(b"k", body, hashlib.sha256).hexdigest()
    assert TributeProvider().verify_webhook({"x-tribute-signature": sig}, body) is None


# --- Stripe: SDK verifies the signature (construct_event); we monkeypatch it -------
def test_stripe_valid_signature_paid(monkeypatch):
    import stripe

    event = {"type": "checkout.session.completed",
             "data": {"object": {"payment_status": "paid", "id": "cs_1",
                                  "amount_total": 1500,
                                  "metadata": {"payload": "buy:image_pack"}}}}
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda body, sig, secret: event)
    ev = StripeProvider().verify_webhook({"stripe-signature": "t=1,v1=ok"}, b"{}")
    assert ev is not None
    assert ev.gateway == "stripe" and ev.gateway_tx_id == "cs_1"
    assert ev.amount == 1500 and ev.payload == "buy:image_pack"


def test_stripe_forged_signature_raises(monkeypatch):
    import stripe

    def _boom(body, sig, secret):
        raise ValueError("signature mismatch")

    monkeypatch.setattr(stripe.Webhook, "construct_event", _boom)
    with pytest.raises(PaymentError):
        StripeProvider().verify_webhook({"stripe-signature": "bad"}, b"{}")


def test_stripe_unpaid_session_is_none(monkeypatch):
    import stripe

    event = {"type": "checkout.session.completed",
             "data": {"object": {"payment_status": "unpaid", "id": "cs_2"}}}
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)
    # `completed` can fire before async funds clear — must not activate.
    assert StripeProvider().verify_webhook({"stripe-signature": "x"}, b"{}") is None


def test_stripe_other_event_is_none(monkeypatch):
    import stripe

    monkeypatch.setattr(stripe.Webhook, "construct_event",
                        lambda *a, **k: {"type": "payment_intent.created",
                                         "data": {"object": {}}})
    assert StripeProvider().verify_webhook({"stripe-signature": "x"}, b"{}") is None


# --- YooKassa: unsigned body → authoritative re-fetch is the ONLY trust source -----
def test_yookassa_non_succeeded_event_is_none():
    body = json.dumps({"event": "payment.canceled", "object": {"id": "p1"}}).encode()
    assert YooKassaProvider().verify_webhook({}, body) is None


def test_yookassa_succeeded_unconfigured_refuses(monkeypatch):
    monkeypatch.setattr(settings, "yookassa_secret", "")
    monkeypatch.setattr(settings, "yookassa_shop_id", "")
    body = json.dumps({"event": "payment.succeeded", "object": {"id": "p1"}}).encode()
    with pytest.raises(PaymentError):
        YooKassaProvider().verify_webhook({}, body)


def test_yookassa_succeeded_missing_id_refuses(monkeypatch):
    monkeypatch.setattr(settings, "yookassa_secret", "sec")
    monkeypatch.setattr(settings, "yookassa_shop_id", "shop")
    body = json.dumps({"event": "payment.succeeded", "object": {}}).encode()
    with pytest.raises(PaymentError):
        YooKassaProvider().verify_webhook({}, body)


def test_yookassa_body_is_not_trusted_server_truth_wins(monkeypatch):
    """The forged body claims a huge amount; the authenticated re-fetch reports the
    real one. The PaymentEvent must reflect the SERVER value, never the body."""
    monkeypatch.setattr(settings, "yookassa_secret", "sec")
    monkeypatch.setattr(settings, "yookassa_shop_id", "shop")

    class _Amount:
        value = "150.00"

    class _Remote:
        status = "succeeded"
        amount = _Amount()
        metadata = {"payload": "sub:premium:3"}
        payment_method = None

    from yookassa import Payment
    monkeypatch.setattr(Payment, "find_one", lambda pid: _Remote())

    body = json.dumps({"event": "payment.succeeded",
                       "object": {"id": "pay_9", "amount": {"value": "999999.00"},
                                  "metadata": {"payload": "evil:grant_admin"}}}).encode()
    ev = YooKassaProvider().verify_webhook({}, body)
    assert ev is not None
    assert ev.gateway_tx_id == "pay_9"
    assert ev.amount == 15000          # 150.00 from the server, NOT 999999 from body
    assert ev.payload == "sub:premium:3"   # server metadata, NOT the body's "evil:..."


def test_yookassa_refetch_failure_is_retryable(monkeypatch):
    monkeypatch.setattr(settings, "yookassa_secret", "sec")
    monkeypatch.setattr(settings, "yookassa_shop_id", "shop")

    def _network_error(pid):
        raise RuntimeError("connection reset")

    from yookassa import Payment
    monkeypatch.setattr(Payment, "find_one", _network_error)

    body = json.dumps({"event": "payment.succeeded", "object": {"id": "pay_x"}}).encode()
    # Transient verify failure must be retryable (503 → YooKassa retries), not a hard reject.
    with pytest.raises(PaymentRetryable):
        YooKassaProvider().verify_webhook({}, body)
