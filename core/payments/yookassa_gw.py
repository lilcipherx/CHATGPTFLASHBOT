"""YooKassa (ЮКасса) provider — RUB cards. Lazy SDK import."""
from __future__ import annotations

import json
import uuid
from decimal import Decimal, InvalidOperation

import structlog

from core.config import settings
from core.payments.base import (
    CheckoutResult,
    PaymentError,
    PaymentEvent,
    PaymentRetryable,
    SavedMethod,
)

log = structlog.get_logger()


def _build_receipt(amount_minor: int, currency: str, description: str) -> dict | None:
    """Build a 54-ФЗ fiscal receipt object for the YooKassa payment request, or
    None when receipts are disabled / not applicable. Pure (no network) so it is
    unit-testable. Never raises — a receipt must never break checkout, so any
    failure logs and degrades to no receipt (None)."""
    try:
        if not settings.yookassa_receipt_enabled or currency != "RUB":
            return None
        contact = (settings.yookassa_receipt_contact or "").strip()
        # email vs phone branch: "@" => email, else strip to digits for phone.
        if "@" in contact:
            customer = {"email": contact}
        else:
            digits = "".join(ch for ch in contact if ch.isdigit())
            customer = {"phone": digits}
        receipt: dict = {
            "customer": customer,
            "items": [
                {
                    # YooKassa caps the line description at 128 chars.
                    "description": description[:128],
                    "quantity": "1.00",
                    "amount": {"value": f"{amount_minor / 100:.2f}", "currency": "RUB"},
                    "vat_code": settings.yookassa_vat_code,
                    "payment_mode": "full_prepayment",
                    "payment_subject": "service",
                }
            ],
        }
        if settings.yookassa_tax_system_code is not None:
            receipt["tax_system_code"] = settings.yookassa_tax_system_code
        return receipt
    except Exception as exc:  # noqa: BLE001 — receipt must never break checkout
        log.warning("yookassa.receipt_build_failed", error=str(exc))
        return None


class YooKassaProvider:
    name = "yookassa"

    def is_available(self) -> bool:
        return bool(settings.yookassa_shop_id and settings.yookassa_secret)

    async def create_checkout(
        self, *, amount: int, currency: str, payload: str, description: str
    ) -> CheckoutResult:
        if not self.is_available():
            raise PaymentError("yookassa not configured")
        # FIX: AUDIT12-19 - wrap sync YooKassa SDK calls in asyncio.to_thread
        import asyncio

        from yookassa import Configuration, Payment

        Configuration.account_id = settings.yookassa_shop_id
        Configuration.secret_key = settings.yookassa_secret
        return_url = settings.miniapp_url or settings.webhook_base_url or "https://t.me"
        body = {
            "amount": {"value": f"{amount / 100:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": description,
            "metadata": {"payload": payload},
        }
        if payload.startswith("sub:"):
            body["save_payment_method"] = True
        receipt = _build_receipt(amount, currency, description)
        if receipt is not None:
            body["receipt"] = receipt
        payment = await asyncio.to_thread(
            Payment.create, body, uuid.uuid4().hex,
        )
        return CheckoutResult(url=payment.confirmation.confirmation_url, gateway_tx_id=payment.id)

    async def charge_saved(
        self,
        *,
        token: str,
        customer_id: str | None = None,
        amount: int,
        currency: str,
        description: str,
        payload: str,
        idempotency_key: str | None = None,
    ) -> str:
        """Charge a previously-saved YooKassa method off-session (auto-renewal).

        ``token`` is the vaulted ``payment_method_id``. Returns the new payment id on
        a captured success; raises PaymentError if the gateway declines or the charge
        does not settle synchronously (off-session, so a 3DS-pending result is a
        failure for our purposes).

        A deterministic ``idempotency_key`` makes a retried renewal charge return the
        SAME payment rather than creating a second one (YooKassa dedupes on it)."""
        if not self.is_available():
            raise PaymentError("yookassa not configured")
        import asyncio

        from yookassa import Configuration, Payment

        Configuration.account_id = settings.yookassa_shop_id
        Configuration.secret_key = settings.yookassa_secret
        body = {
            "amount": {"value": f"{amount / 100:.2f}", "currency": "RUB"},
            "capture": True,
            "payment_method_id": token,
            "description": description,
            "metadata": {"payload": payload},
        }
        receipt = _build_receipt(amount, currency, description)
        if receipt is not None:
            body["receipt"] = receipt
        try:
            payment = await asyncio.to_thread(
                Payment.create, body, idempotency_key or uuid.uuid4().hex,
            )
        except Exception as exc:  # network / declined
            raise PaymentError(f"yookassa recurring charge failed: {exc}") from exc
        if getattr(payment, "status", None) != "succeeded":
            raise PaymentError(
                f"yookassa recurring charge not settled: {getattr(payment, 'status', '?')}"
            )
        return str(getattr(payment, "id", "") or "")

    async def refund(self, *, gateway_tx_id: str, amount: int) -> str:
        """Refund a YooKassa payment by id for ``amount`` kopecks. Raises
        PaymentError on failure so the caller keeps the tx in refund_pending."""
        if not self.is_available():
            raise PaymentError("yookassa not configured")
        import asyncio

        from yookassa import Configuration, Refund

        Configuration.account_id = settings.yookassa_shop_id
        Configuration.secret_key = settings.yookassa_secret
        try:
            # FIX: AUDIT12-32 - deterministic idempotency key (was: random UUID).
            refund = await asyncio.to_thread(
                Refund.create,
                {
                    "payment_id": gateway_tx_id,
                    "amount": {"value": f"{amount / 100:.2f}", "currency": "RUB"},
                },
                f"refund:{gateway_tx_id}",
            )
        except Exception as exc:
            raise PaymentError(f"yookassa refund failed: {exc}") from exc
        return str(getattr(refund, "id", "") or "")

    def verify_webhook(self, headers: dict, body: bytes) -> PaymentEvent | None:
        # YooKassa does NOT sign its webhooks, so the notification body is
        # UNTRUSTED. The ONLY authoritative check is re-fetching the payment from
        # the API (authenticated with the shop secret) and using ITS server-side
        # status / amount / metadata — never the body. The body is used solely for
        # the payment id, which the lookup then validates.
        # FIX: F29 - a malformed/non-JSON body (proxy corruption, non-YooKassa source
        # that cleared the IP allow-list) raises JSONDecodeError, which is NOT in the
        # webhook protocol contract (PaymentEvent | None | PaymentError | PaymentRetryable)
        # and would surface as a raw 5xx → YooKassa retries forever. Convert to PaymentError.
        try:
            data = json.loads(body or b"{}")
        except (ValueError, TypeError) as exc:
            raise PaymentError(f"yookassa webhook: malformed JSON body ({exc})") from exc
        obj = data.get("object", {})
        if data.get("event") != "payment.succeeded":
            return None
        payment_id = obj.get("id", "")

        # If we cannot perform that authoritative re-fetch — the gateway isn't
        # configured, or the notification carries no payment id — we must REFUSE
        # rather than fall back to trusting the body. Otherwise a forged
        # "payment.succeeded" that merely cleared the source-IP allow-list would be
        # accepted at face value (granting access / crediting on attacker input).
        if not self.is_available():
            raise PaymentError("yookassa not configured — cannot verify webhook")
        if not payment_id:
            raise PaymentError("yookassa webhook missing payment id")

        from yookassa import Configuration, Payment

        Configuration.account_id = settings.yookassa_shop_id
        Configuration.secret_key = settings.yookassa_secret
        try:
            # NOTE: this SDK call is synchronous. verify_webhook itself is a sync
            # method on the gateway base class — the async webhook ROUTER wraps
            # the entire call in asyncio.to_thread so this block runs in a worker
            # thread and never blocks the event loop. See api/routers/webhooks.py.
            remote = Payment.find_one(payment_id)
        except Exception as exc:  # network / auth — transient, ask YooKassa to retry
            raise PaymentRetryable(f"yookassa verify failed: {exc}") from exc
        if getattr(remote, "status", None) != "succeeded":
            return None

        # Server-side truth only — the notification body is never trusted here.
        # FIX: U10 - defensive: a malformed remote object (missing amount/metadata)
        # should raise PaymentError, not AttributeError.
        metadata = getattr(remote, "metadata", None) or {}
        amount_obj = getattr(remote, "amount", None)
        if amount_obj is None or getattr(amount_obj, "value", None) is None:
            raise PaymentError("yookassa webhook: missing amount on remote payment")
        try:
            # FIX: AUDIT13-M4 - parse the authoritative amount via Decimal, not binary
            # float, so a value that isn't exactly representable can't land on the wrong
            # side of round() and diverge by a kopeck from the quoted price (mirrors
            # crypto_gw's Decimal handling — this was the last money path still on float).
            amount_minor = int((Decimal(str(amount_obj.value)) * 100).quantize(Decimal("1")))
        except (TypeError, ValueError, InvalidOperation) as exc:
            raise PaymentError(f"yookassa webhook: bad amount value {amount_obj.value!r}") from exc
        return PaymentEvent(
            payload=metadata.get("payload", ""),
            gateway=self.name,
            gateway_tx_id=payment_id,
            amount=amount_minor,
            status="paid",
            saved_method=_extract_saved_method(remote),
        )


def _extract_saved_method(remote: object) -> SavedMethod | None:
    """Pull the vaulted payment_method_id off a re-fetched YooKassa payment, or None.

    Only methods YooKassa actually saved (``payment_method.saved``) are reusable.
    Never raises — token capture must never break a real activation."""
    try:
        pm = getattr(remote, "payment_method", None)
        if pm is None or not getattr(pm, "saved", False):
            return None
        token = str(getattr(pm, "id", "") or "")
        if not token:
            return None
        card = getattr(pm, "card", None)
        return SavedMethod(
            token=token,
            brand=getattr(card, "card_type", None) if card is not None else None,
            last4=getattr(card, "last4", None) if card is not None else None,
        )
    except Exception:  # noqa: BLE001 — best-effort; activation must still proceed
        return None
