"""Crypto payments via @CryptoBot (Crypto Pay API).

Flow mirrors the other external gateways: createInvoice (fiat USD, auto-converted
to the crypto the user picks at pay time) → pay link → signed webhook → idempotent
activation. The webhook is authenticated by the documented HMAC-SHA256 scheme:
secret = SHA256(token); signature = HMAC_SHA256(secret, raw_body); compared to the
``crypto-pay-api-signature`` header — so a forged "invoice_paid" is rejected.

Amounts: the rest of the app quotes in USD minor units (cents, like Stripe — see
payments.service.stars_to_minor). We create the invoice in USD dollars and report
the paid amount back in cents, so apply_event's amount check works unchanged.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from core.config import settings
from core.payments.base import CheckoutResult, PaymentError, PaymentEvent

_MAINNET = "https://pay.crypt.bot/api"
_TESTNET = "https://testnet-pay.crypt.bot/api"


class CryptoBotProvider:
    name = "crypto"

    def _base(self) -> str:
        return _TESTNET if settings.crypto_pay_testnet else _MAINNET

    def is_available(self) -> bool:
        return bool(settings.crypto_pay_token)

    async def create_checkout(
        self, *, amount: int, currency: str, payload: str, description: str
    ) -> CheckoutResult:
        if not self.is_available():
            raise PaymentError("crypto pay not configured")
        import httpx

        # amount comes in USD minor units (cents); Crypto Pay fiat invoices take a
        # decimal string in the fiat unit. currency_type=fiat lets the user pay in
        # any enabled crypto, converted at pay time.
        usd = f"{amount / 100:.2f}"
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(
                f"{self._base()}/createInvoice",
                headers={"Crypto-Pay-API-Token": settings.crypto_pay_token},
                json={
                    "currency_type": "fiat",
                    "fiat": "USD",
                    "amount": usd,
                    "description": description[:1024],
                    "payload": payload,
                    "allow_anonymous": False,
                },
            )
            r.raise_for_status()
            data = r.json()
        if not data.get("ok"):
            raise PaymentError(f"crypto pay error: {data.get('error')}")
        inv = data["result"]
        url = inv.get("bot_invoice_url") or inv.get("pay_url") or inv.get("mini_app_invoice_url")
        if not url:
            raise PaymentError("crypto pay: no pay url in response")
        return CheckoutResult(url=url, gateway_tx_id=str(inv["invoice_id"]))

    async def refund(self, *, gateway_tx_id: str, amount: int) -> str:
        # Crypto Pay has no programmatic refund API for paid invoices — refunds are
        # manual. Raise so the caller keeps the tx in refund_pending (entitlement is
        # still revoked DB-side); an operator settles the crypto refund out of band.
        raise PaymentError("crypto refund must be done manually in @CryptoBot")

    def verify_webhook(self, headers: dict, body: bytes) -> PaymentEvent | None:
        if not self.is_available():
            raise PaymentError("crypto pay not configured — cannot verify webhook")
        received = headers.get("crypto-pay-api-signature", "")
        secret = hashlib.sha256(settings.crypto_pay_token.encode()).digest()
        calc = hmac.new(secret, body, hashlib.sha256).hexdigest()
        if not received or not hmac.compare_digest(calc, received):
            raise PaymentError("crypto pay signature invalid")

        try:
            update = json.loads(body or b"{}")
        except json.JSONDecodeError as exc:
            raise PaymentError("crypto pay bad json") from exc
        if update.get("update_type") != "invoice_paid":
            return None
        inv = update.get("payload") or {}
        if inv.get("status") != "paid":
            return None
        # Paid fiat invoice: `amount` is the USD figure we set → back to cents.
        # FIX: AUDIT-18 - use Decimal for monetary amount (avoid float precision loss)

        from decimal import Decimal, InvalidOperation

        try:

            cents = int((Decimal(str(inv.get("amount", "0"))) * 100).to_integral_value())

        except (TypeError, ValueError, InvalidOperation):

            cents = 0
        return PaymentEvent(
            payload=inv.get("payload", ""),
            gateway=self.name,
            gateway_tx_id=str(inv.get("invoice_id", "")),
            amount=cents,
            status="paid",
        )
