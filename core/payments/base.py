"""PaymentProvider abstraction (§9 of the plan).

Each external gateway implements:
    create_checkout(amount, currency, payload, description) -> CheckoutResult
    verify_webhook(headers, body) -> PaymentEvent | None

Telegram Stars is handled natively in the bot (aiogram invoices), so it is not a
PaymentProvider here — only the 3 external gateways are."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


def gateway_currency(gateway: str) -> str:
    """The ledger currency a gateway charges in (lowercase, matching the existing
    'stars'/'rub' convention). Mirrors stars_to_minor: Stripe + Crypto Pay are priced
    in USD, YooKassa/СБП(Tribute) in RUB, Telegram Stars in 'stars'. A single source so
    the transactions ledger never mislabels the unit."""
    if gateway == "stars":
        return "stars"
    if gateway in ("stripe", "crypto"):
        return "usd"
    return "rub"


@dataclass
class CheckoutResult:
    url: str
    gateway_tx_id: str


@dataclass
class SavedMethod:
    """A reusable payment token captured at checkout so Premium auto-renewal can
    charge recurringly without user interaction (ТЗ §6). The ids are gateway-
    specific opaque strings; ``brand``/``last4`` are display-only and optional."""
    token: str                       # YooKassa payment_method_id | Stripe payment_method
    customer_id: str | None = None   # Stripe customer the method is attached to; None for YooKassa
    brand: str | None = None
    last4: str | None = None


@dataclass
class PaymentEvent:
    payload: str           # "sub:<uid>:premium:3" | "pack:<uid>:image_pack:100" | "avatar:<uid>"
    gateway: str
    gateway_tx_id: str
    amount: int
    status: str            # paid | failed | pending
    # Set only on a subscription checkout the gateway saved a reusable token for
    # (None otherwise). apply_event persists it for the auto-renewal cron.
    saved_method: SavedMethod | None = None


class PaymentError(Exception):
    """Definitive webhook rejection (bad signature / forgery / unparseable). The
    caller should ACK (HTTP 200) so the gateway does not retry a request that will
    never be accepted."""


class PaymentRetryable(PaymentError):
    """Transient verification failure (e.g. the authoritative re-fetch timed out or
    the gateway API was unreachable). The caller should return 5xx so the gateway
    RETRIES delivery — a real but unverified payment must not be dropped."""


@runtime_checkable
class PaymentProvider(Protocol):
    name: str

    def is_available(self) -> bool: ...

    async def create_checkout(
        self, *, amount: int, currency: str, payload: str, description: str
    ) -> CheckoutResult: ...

    def verify_webhook(self, headers: dict, body: bytes) -> PaymentEvent | None: ...

    async def refund(self, *, gateway_tx_id: str, amount: int) -> str:
        """Reverse a captured payment at the gateway (full refund of ``amount``
        minor units). Returns the gateway's refund id, or raises PaymentError so
        the caller can keep the transaction in ``refund_pending`` and retry."""
        ...
