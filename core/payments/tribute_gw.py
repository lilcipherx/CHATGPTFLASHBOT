"""Tribute (СБП / Faster Payments) provider.

⚠️ UNVERIFIED INTEGRATION. Tribute's exact REST endpoints and webhook field names
are NOT confirmed against its official docs. This implements the *common* shape —
create a payment link via REST, verify webhooks with an HMAC-SHA256 signature over
the raw body using the API key — but the field mapping below (``payment_url``,
``id``, ``status``, ``metadata.payload``, header ``x-tribute-signature``) is a
best guess and MUST be checked against the live API before going live.

To avoid SILENTLY accepting or dropping real money through a wrong mapping, the
gateway is INERT until ``TRIBUTE_API_VERIFIED=true`` is set by an operator who has
confirmed the mapping (``is_available()`` gates both checkout and webhook
handling). Until then it offers no checkout and applies no webhook — and every
skipped/odd-shaped webhook is logged loudly instead of returning a quiet ``None``.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import structlog

from core.config import settings
from core.payments.base import CheckoutResult, PaymentError, PaymentEvent

log = structlog.get_logger()


class TributeProvider:
    name = "sbp_tribute"
    _BASE = "https://tribute.tg/api/v1"

    def is_available(self) -> bool:
        # Require BOTH a key and an explicit "I verified the API" acknowledgement,
        # so an unverified mapping can never silently move money.
        return bool(settings.tribute_api_key and settings.tribute_api_verified)

    async def create_checkout(
        self, *, amount: int, currency: str, payload: str, description: str
    ) -> CheckoutResult:
        if not self.is_available():
            raise PaymentError("tribute not configured")
        import httpx

        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(
                f"{self._BASE}/payments",
                headers={"Authorization": f"Bearer {settings.tribute_api_key}"},
                json={
                    "amount": amount,  # kopecks
                    "currency": "RUB",
                    "description": description,
                    "metadata": {"payload": payload},
                },
            )
            r.raise_for_status()
            data = r.json()
        return CheckoutResult(url=data["payment_url"], gateway_tx_id=str(data["id"]))

    async def refund(self, *, gateway_tx_id: str, amount: int) -> str:
        # Tribute's refund API shape is unconfirmed (see module docstring); fail
        # loudly so the admin issues it manually and the tx stays refund_pending.
        raise PaymentError("tribute refund must be issued manually (API unconfirmed)")

    def verify_webhook(self, headers: dict, body: bytes) -> PaymentEvent | None:
        # Inert until the integration is verified: refuse to apply a webhook we
        # might be mis-parsing rather than credit/deny access on a wrong mapping.
        if not self.is_available():
            log.warning(
                "tribute.webhook_ignored_unverified",
                reason="set TRIBUTE_API_VERIFIED=true after confirming the API",
            )
            return None

        signature = headers.get("x-tribute-signature") or headers.get("X-Tribute-Signature", "")
        expected = hmac.new(
            settings.tribute_api_key.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise PaymentError("tribute signature invalid")

        # FIX: F30 - a malformed body would raise JSONDecodeError (not in the webhook
        # protocol contract) and surface as a 5xx → infinite retries. Convert to PaymentError.
        try:
            data = json.loads(body or b"{}")
        except (ValueError, TypeError) as exc:
            raise PaymentError(f"tribute webhook: malformed JSON body ({exc})") from exc
        status = data.get("status")
        if status not in {"paid", "succeeded", "completed"}:
            # Signature was valid but the body isn't the shape we expect. Log the
            # actual keys so a field-name mismatch is diagnosable instead of
            # vanishing as a silent no-op (the original failure mode).
            log.warning("tribute.webhook_unrecognized", status=status, keys=sorted(data.keys()))
            return None
        payload = data.get("metadata", {}).get("payload", "")
        if not payload:
            # Paid event we can't attribute to a user → apply_event will drop it.
            log.error("tribute.webhook_no_payload", keys=sorted(data.keys()))
        return PaymentEvent(
            payload=payload,
            gateway=self.name,
            gateway_tx_id=str(data.get("id", "")),
            amount=int(data.get("amount", 0)),
            status="paid",
        )
