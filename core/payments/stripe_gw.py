"""Stripe provider — international cards. Checkout Session + signed webhook."""
from __future__ import annotations

from core.config import settings
from core.payments.base import (
    CheckoutResult,
    PaymentError,
    PaymentEvent,
    SavedMethod,
)


class StripeProvider:
    name = "stripe"

    def is_available(self) -> bool:
        return bool(settings.stripe_secret)

    async def create_checkout(
        self, *, amount: int, currency: str, payload: str, description: str
    ) -> CheckoutResult:
        if not self.is_available():
            raise PaymentError("stripe not configured")
        # FIX: AUDIT12-18 - wrap ALL sync stripe.* calls in asyncio.to_thread
        # so they don't block the event loop.
        import asyncio
        import stripe

        stripe.api_key = settings.stripe_secret
        success_url = settings.miniapp_url or settings.webhook_base_url or "https://t.me"
        extra: dict = {}
        if payload.startswith("sub:"):
            extra["customer_creation"] = "always"
            extra["payment_intent_data"] = {"setup_future_usage": "off_session"}
        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "product_data": {"name": description},
                        "unit_amount": amount,
                    },
                    "quantity": 1,
                }
            ],
            metadata={"payload": payload},
            success_url=success_url,
            cancel_url=success_url,
            **extra,
        )
        return CheckoutResult(url=session.url, gateway_tx_id=session.id)

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
        """Charge a saved Stripe method off-session (auto-renewal).

        ``token`` is the ``payment_method`` id, ``customer_id`` the customer it is
        attached to. Returns the PaymentIntent id on success; raises PaymentError if
        the card is declined or authentication is required (off-session can't prompt).

        A deterministic ``idempotency_key`` makes a retried renewal charge return the
        SAME PaymentIntent instead of creating a second one (Stripe dedupes on it)."""
        if not self.is_available():
            raise PaymentError("stripe not configured")
        import asyncio
        import stripe

        stripe.api_key = settings.stripe_secret
        try:
            intent = await asyncio.to_thread(
                stripe.PaymentIntent.create,
                amount=amount,
                currency=currency.lower(),
                customer=customer_id,
                payment_method=token,
                off_session=True,
                confirm=True,
                description=description,
                metadata={"payload": payload},
                **({"idempotency_key": idempotency_key} if idempotency_key else {}),
            )
        except Exception as exc:  # CardError (declined / authentication_required) / network
            raise PaymentError(f"stripe off-session charge failed: {exc}") from exc
        if getattr(intent, "status", None) != "succeeded":
            raise PaymentError(
                f"stripe off-session charge not settled: {getattr(intent, 'status', '?')}"
            )
        return str(getattr(intent, "id", "") or "")

    async def refund(self, *, gateway_tx_id: str, amount: int) -> str:
        """Full refund of a Checkout Session. ``gateway_tx_id`` is the Session id;
        resolve its PaymentIntent and refund that. Raises PaymentError on failure
        so the caller leaves the tx in refund_pending and can retry."""
        if not self.is_available():
            raise PaymentError("stripe not configured")
        import asyncio
        import stripe

        stripe.api_key = settings.stripe_secret
        try:
            session = await asyncio.to_thread(
                stripe.checkout.Session.retrieve, gateway_tx_id
            )
            payment_intent = getattr(session, "payment_intent", None) or (
                session.get("payment_intent") if hasattr(session, "get") else None
            )
            if not payment_intent:
                raise PaymentError("stripe: session has no payment_intent")
            # FIX: AUDIT12-31 - deterministic idempotency key prevents double-refund.
            refund = await asyncio.to_thread(
                stripe.Refund.create,
                payment_intent=payment_intent,
                amount=amount,  # FIX: AUDIT-178 - honor amount param
                idempotency_key=f"refund:{gateway_tx_id}",
            )
        except PaymentError:
            raise
        except Exception as exc:  # network / already-refunded / disputed
            raise PaymentError(f"stripe refund failed: {exc}") from exc
        return str(getattr(refund, "id", "") or "")

    def verify_webhook(self, headers: dict, body: bytes) -> PaymentEvent | None:
        import stripe

        sig = headers.get("stripe-signature") or headers.get("Stripe-Signature", "")
        try:
            event = stripe.Webhook.construct_event(
                body, sig, settings.stripe_webhook_secret
            )
        except Exception as exc:  # signature mismatch / bad payload
            raise PaymentError(f"stripe signature invalid: {exc}") from exc

        if event["type"] != "checkout.session.completed":
            return None
        obj = event["data"]["object"]
        # `completed` can fire for asynchronous payment methods before funds clear
        # (payment_status="unpaid"/"no_payment_required"). Only activate on a real
        # paid session, so we never grant access ahead of the money.
        if obj.get("payment_status") != "paid":
            return None
        payload = obj.get("metadata", {}).get("payload", "")
        return PaymentEvent(
            payload=payload,
            gateway=self.name,
            gateway_tx_id=obj.get("id", ""),
            amount=obj.get("amount_total", 0),
            status="paid",
            saved_method=self._saved_from_session(obj, payload),
        )

    def _saved_from_session(self, session_obj: dict, payload: str) -> SavedMethod | None:
        """Read the vaulted customer + payment_method off a completed subscription
        Checkout Session, or None. The session only carries the customer + a
        payment_intent ref, so we retrieve the PaymentIntent for its payment_method.
        Never raises — token capture must never break a real activation."""
        if not payload.startswith("sub:"):
            return None
        try:
            import stripe

            customer = session_obj.get("customer")
            pi_id = session_obj.get("payment_intent")
            if not (customer and pi_id):
                return None
            stripe.api_key = settings.stripe_secret
            # NOTE: stripe SDK is synchronous. verify_webhook → _saved_from_session
            # is a sync call chain; the async webhook ROUTER wraps the entire
            # verify_webhook call in asyncio.to_thread so this block runs in a
            # worker thread and never blocks the event loop. See api/routers/webhooks.py.
            intent = stripe.PaymentIntent.retrieve(pi_id)
            pm = getattr(intent, "payment_method", None) or (
                intent.get("payment_method") if hasattr(intent, "get") else None
            )
            if not pm:
                return None
            return SavedMethod(token=str(pm), customer_id=str(customer))
        except Exception:  # noqa: BLE001 — best-effort; activation must still proceed
            return None
