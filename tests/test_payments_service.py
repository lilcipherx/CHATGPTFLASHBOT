"""core.payments.service dispatcher + pricing helpers (Loop coverage): the checkout
dispatch, the quoted-minor payload embed (anti price-drift), stars→minor conversion,
the amount-expectation table, and off-session charge delegation. All pure / dispatcher
logic — providers and settings are stubbed, no network.
"""
from __future__ import annotations

import types

import pytest

from core.config import settings
from core.payments import service
from core.payments.base import CheckoutResult, PaymentError


def test_stars_to_minor_usd_vs_rub(monkeypatch):
    monkeypatch.setattr(settings, "stars_to_usd", 0.02)
    monkeypatch.setattr(settings, "stars_to_rub", 1.5)
    usd, cur = service.stars_to_minor(100, "stripe")  # USD gateway
    assert cur == "USD" and usd == int(round(100 * 0.02 * 100))
    rub, cur2 = service.stars_to_minor(100, "yookassa")  # RUB gateway
    assert cur2 == "RUB" and rub == int(round(100 * 1.5 * 100))


async def test_create_checkout_embeds_quoted_minor_in_payload(monkeypatch):
    captured: dict = {}

    class FakeProvider:
        def is_available(self):
            return True

        async def create_checkout(self, *, amount, currency, payload, description):
            captured.update(amount=amount, currency=currency, payload=payload)
            return CheckoutResult(url="https://pay/x", gateway_tx_id="tx1")

    monkeypatch.setattr(service, "get_provider", lambda g: FakeProvider())
    monkeypatch.setattr(settings, "stars_to_usd", 0.02)

    res = await service.create_checkout(
        "stripe", stars_price=100, payload="sub:1:pro:1", description="Pro"
    )
    assert res.gateway_tx_id == "tx1"
    # The QUOTED minor amount is appended so apply_event validates the paid webhook
    # against the quote, not the live price table.
    assert captured["payload"] == f"sub:1:pro:1:{captured['amount']}"


async def test_create_checkout_unavailable_raises(monkeypatch):
    monkeypatch.setattr(service, "get_provider", lambda g: None)
    with pytest.raises(PaymentError):
        await service.create_checkout(
            "stripe", stars_price=1, payload="x", description="y"
        )


def test_expected_minor_avatar_and_unknown(monkeypatch):
    monkeypatch.setattr(settings, "stars_to_usd", 0.02)
    # avatar is a fixed price → a concrete minor amount.
    assert service._expected_minor("stripe", "avatar", ["avatar", "1"]) is not None
    # unknown product / bad shape → None (webhook amount can't be validated → rejected).
    assert service._expected_minor("stripe", "sub", ["sub", "1", "NOPE", "1"]) is None
    assert service._expected_minor("stripe", "bogus", ["bogus"]) is None


async def test_charge_saved_method_delegates_and_skips(monkeypatch):
    method = types.SimpleNamespace(gateway="stripe", token="pm_1", customer_id="cus_1")

    class WithCharge:
        async def charge_saved(self, **kw):
            assert kw["token"] == "pm_1" and kw["idempotency_key"] == "k"
            return "pi_new"

    monkeypatch.setattr(service, "get_provider", lambda g: WithCharge())
    got = await service.charge_saved_method(
        method, amount=500, currency="USD", description="renew",
        payload="sub:1:pro:1", idempotency_key="k",
    )
    assert got == "pi_new"

    # A gateway with no recurring support (no charge_saved) → None, not an error.
    class NoCharge:
        pass

    monkeypatch.setattr(service, "get_provider", lambda g: NoCharge())
    assert await service.charge_saved_method(
        method, amount=1, currency="USD", description="d", payload="p"
    ) is None
