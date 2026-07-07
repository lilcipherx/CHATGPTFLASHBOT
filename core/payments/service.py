"""Checkout creation + webhook event application for external gateways.

Payloads embed the user_id (external webhooks have no Telegram context):
    sub:<uid>:<product>:<months>
    pack:<uid>:<pack>:<qty>
    avatar:<uid>
Activation routes to the billing service, which is idempotent on gateway_tx_id."""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.constants import (
    AVATAR_PRICE,
    CREDIT_PACKS,
    PACK_PRICES,
    SUBSCRIPTION_PRICES,
)
from core.payments import PaymentError, PaymentEvent, get_provider
from core.payments.base import CheckoutResult
from core.services.billing import (
    activate_subscription,
    add_credits,
    add_pack_credits,
    record_one_time,
)
from core.services.users import get_user

log = structlog.get_logger()


def stars_to_minor(stars: int, gateway: str) -> tuple[int, str]:
    """Convert a Stars price to minor fiat units + currency for the gateway."""
    # Stripe + Crypto Pay are priced in USD; the rest (YooKassa/СБП) in RUB.
    if gateway in ("stripe", "crypto"):
        return int(round(stars * settings.stars_to_usd * 100)), "USD"
    return int(round(stars * settings.stars_to_rub * 100)), "RUB"


async def create_checkout(
    gateway: str, *, stars_price: int, payload: str, description: str
) -> CheckoutResult:
    provider = get_provider(gateway)
    if provider is None or not provider.is_available():
        raise PaymentError(f"{gateway} unavailable")
    amount, currency = stars_to_minor(stars_price, gateway)
    # Embed the QUOTED minor amount in the payload (echoed back verbatim by the
    # gateway in the webhook). apply_event validates the paid amount against this
    # quote, NOT the live price table — so an admin changing a price or fx rate
    # between checkout and payment can never reject a legitimately paid webhook.
    return await provider.create_checkout(
        amount=amount, currency=currency,
        payload=f"{payload}:{amount}", description=description,
    )


def _expected_minor(gateway: str, kind: str, parts: list[str]) -> int | None:
    """Expected amount (in the gateway's minor fiat units) for this payload, or
    None if the product/qty/duration is unknown. Defence-in-depth: a webhook with
    an amount that doesn't match our own price table is rejected, even though the
    checkout was server-created and the webhook is signed/IP-restricted."""
    stars: int | None = None
    if kind == "sub" and len(parts) == 4 and parts[3].isdigit():
        stars = SUBSCRIPTION_PRICES.get(parts[2], {}).get(int(parts[3]))
    elif kind == "pack" and len(parts) == 4 and parts[3].isdigit():
        stars = PACK_PRICES.get(parts[2], {}).get(int(parts[3]))
    elif kind == "credits" and len(parts) == 3 and parts[2].isdigit():
        stars = CREDIT_PACKS.get(int(parts[2]))
    elif kind == "avatar":
        stars = AVATAR_PRICE
    if stars is None:
        return None
    minor, _ = stars_to_minor(stars, gateway)
    return minor


async def charge_saved_method(
    method, *, amount: int, currency: str, description: str, payload: str,
    idempotency_key: str | None = None,
) -> str | None:
    """Charge a saved PaymentMethod off-session via its gateway (auto-renewal).

    Returns the new gateway tx id on success, or None if the gateway has no recurring
    support (Stars / СБП / Crypto have no ``charge_saved``). Raises PaymentError if a
    capable gateway declines the charge.

    ``idempotency_key`` (when given) is forwarded to the gateway so a retried charge
    for the SAME renewal period is deduplicated by the gateway — without it a crash
    between a successful charge and the local sub-extension would re-charge the user
    on the next sweep."""
    provider = get_provider(method.gateway)
    charge = getattr(provider, "charge_saved", None)
    if provider is None or charge is None:
        return None
    return await charge(
        token=method.token,
        customer_id=method.customer_id,
        amount=amount,
        currency=currency,
        description=description,
        payload=payload,
        idempotency_key=idempotency_key,
    )


async def apply_event(session: AsyncSession, event: PaymentEvent) -> int | None:
    """Activate a verified, paid event. Returns the affected user_id (for
    notification) or None if ignored/duplicate/unparseable."""
    if event.status != "paid" or not event.payload:
        return None

    parts = event.payload.split(":")
    kind = parts[0]
    try:
        uid = int(parts[1])
    except (IndexError, ValueError):
        return None

    # Pop the quoted minor amount create_checkout appended (sub/pack = 4 base
    # fields, credits = 3, avatar = 2; a trailing numeric field beyond that is the
    # quote). Validating against the quote — not the live price — means a price/fx
    # change between checkout and payment can't reject a legitimately paid webhook.
    # Legacy payloads without the trailing quote fall back to the price table.
    _BASE_LEN = {"sub": 4, "pack": 4, "credits": 3, "avatar": 2}
    quoted_minor: int | None = None
    base = _BASE_LEN.get(kind)
    if base is not None and len(parts) == base + 1 and parts[-1].isdigit():
        quoted_minor = int(parts[-1])
        parts = parts[:base]

    # Reject amount tampering / price misconfig (±1 minor unit for fx rounding).
    expected = quoted_minor if quoted_minor is not None else _expected_minor(
        event.gateway, kind, parts
    )
    if expected is None:
        log.warning("payment.unknown_product", gateway=event.gateway, payload=event.payload)
        return None
    if abs(event.amount - expected) > 1:
        log.warning("payment.amount_mismatch", gateway=event.gateway,
                    payload=event.payload, got=event.amount, expected=expected)
        return None

    user = await get_user(session, uid)
    if user is None:
        return None

    if kind == "sub" and len(parts) == 4:
        ok = await activate_subscription(
            session, user, product=parts[2], months=int(parts[3]),
            gateway=event.gateway, amount=event.amount, gateway_tx_id=event.gateway_tx_id,
        )
    elif kind == "pack" and len(parts) == 4:
        ok = await add_pack_credits(
            session, user, pack=parts[2], qty=int(parts[3]),
            gateway=event.gateway, amount=event.amount, gateway_tx_id=event.gateway_tx_id,
        )
    elif kind == "credits" and len(parts) == 3:
        ok = await add_credits(
            session, user, qty=int(parts[2]),
            gateway=event.gateway, amount=event.amount, gateway_tx_id=event.gateway_tx_id,
        )
    elif kind == "avatar":
        ok = await record_one_time(
            session, user, product="avatar",
            gateway=event.gateway, amount=event.amount, gateway_tx_id=event.gateway_tx_id,
        )
    else:
        return None

    # Persist a vaulted payment token captured at a subscription checkout so the
    # auto-renewal cron can charge recurringly (ТЗ §6). Best-effort: a token-store
    # failure must never fail a real, already-applied purchase.
    if kind == "sub" and ok and event.saved_method is not None:
        from core.services import payment_methods

        try:
            await payment_methods.save_method(
                session, user_id=user.user_id, gateway=event.gateway,
                saved=event.saved_method,
            )
        except Exception:  # noqa: BLE001 — token capture must never fail a purchase
            # FIX: R10 - rollback the half-applied save_method so a stale session
            # state can't poison the referral reward / commit below. The purchase
            # itself already committed via _record_tx; we only need to discard the
            # token-insert attempt.
            log.warning("payment.save_method_failed", user_id=user.user_id)
            await session.rollback()
            # FIX: AUDIT-24 - re-fetch user after rollback (session objects are expired).
            # FIX: AUDIT-TEST - use the module-level get_user (line 28); the redundant
            # local `import get_user` here made it a function-local everywhere, so the
            # earlier `get_user(session, uid)` above raised UnboundLocalError.
            user = await get_user(session, user.user_id)

    # Reward the referrer on the referred user's first paid purchase (not avatar —
    # we avoid coupling a referral reward to a one-time service). Run this even when
    # ``ok`` is False (a DUPLICATE webhook for an already-applied purchase): the
    # reward is idempotent on its own (referrals.referred_id is unique), so a retry
    # RECOVERS a reward that was lost when the process died between the purchase
    # commit and the reward commit. Without this, the lost reward is never retried.
    if kind != "avatar":
        from core.services.referrals import (
            notify_referrer,
            reward_referral_on_payment,
        )

        rewarded = await reward_referral_on_payment(session, user)
        if rewarded:
            await notify_referrer(*rewarded, reason="purchase")  # FIX: X5 - was default "register"

    # Congratulate the buyer if this purchase pushed their cumulative spend into a new
    # VIP tier (every product counts). Best-effort, idempotent per tier.
    from core.services.loyalty import check_and_notify_upgrade
    await check_and_notify_upgrade(session, user)
    # Announce any cashback / first-purchase bonus ✨ this purchase earned.
    from core.services.billing import notify_purchase_bonus
    await notify_purchase_bonus(session, user)
    # Spend the user's applied discount code if it was the operative discount.
    from core.services import checkout, pricing, promos
    await promos.consume_discount(session, user, sale_pct=await pricing.sale_percent(session))
    # Close any open abandoned-cart intents — the buyer just completed a purchase.
    await checkout.mark_completed(session, user.user_id)

    return uid if ok else None
