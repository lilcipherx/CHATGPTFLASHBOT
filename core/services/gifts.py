"""Gift purchase + redemption (ТЗ §6).

A buyer pays for a Gift (create_gift, idempotent on the gateway charge id); a
*different* user redeems the generated code (redeem_gift), which applies the
entitlement through the same billing functions a direct purchase uses. Both the
payment and the redemption are idempotent so a webhook / message retry can never
double-grant.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User
from core.models.gift import Gift
from core.services import billing


def generate_code() -> str:
    """An uppercased, URL-safe token used as the shareable gift code. Not
    cryptographically meaningful — just hard enough to guess and easy to type.

    FIX: AUDIT-TEST - MUST be uppercased: redeem_gift() normalizes the entered code
    with .upper() before the DB lookup, so a mixed-case token (the old
    token_urlsafe output) could NEVER be matched → every gift redemption failed.
    Uppercasing at creation keeps generation and redemption case-consistent."""
    return secrets.token_urlsafe(16).upper()  # FIX: AUDIT-174 - ~128 bits entropy


async def create_gift(
    session: AsyncSession,
    *,
    buyer_id: int,
    kind: str,
    product: str,
    months: int | None,
    qty: int | None,
    gateway: str,
    amount: int,
    gateway_tx_id: str | None,
) -> Gift | None:
    """Create a paid Gift and return it (with its code). Idempotent on
    ``gateway_tx_id``: a retry of the same charge returns None instead of minting
    a second gift. Commits."""
    if gateway_tx_id:
        existing = await session.scalar(
            select(Gift).where(Gift.gateway_tx_id == gateway_tx_id)
        )
        if existing is not None:
            return None

    gift = Gift(
        code=generate_code(),
        buyer_id=buyer_id,
        kind=kind,
        product=product,
        months=months,
        qty=qty,
        gateway=gateway,
        amount=amount,
        gateway_tx_id=gateway_tx_id,
        status="paid",
    )
    session.add(gift)
    # FIX: AUDIT-133 - use SAVEPOINT so caller's session isn't poisoned
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        return None
    await session.commit()
    return gift


async def redeem_gift(session: AsyncSession, code: str, user: User) -> tuple[bool, str]:
    """Apply an un-redeemed paid gift identified by ``code`` to ``user``.

    Returns (True, success_message) or (False, reason) for: unknown code, already
    redeemed, or self-redeem (buyer == redeemer). The entitlement is granted via
    billing with gateway="gift"/amount=0 and a deterministic gateway_tx_id so the
    billing-layer idempotency also holds if redemption is retried."""
    norm = (code or "").strip().upper()
    # Lock the gift row (SELECT ... FOR UPDATE) so two concurrent /redeem of the SAME
    # code serialize. The billing layer already blocks a double-grant (deterministic
    # gateway_tx_id), but without the lock both readers pass the status check and the
    # loser is told "activated" while receiving nothing AND overwrites redeemed_by.
    # With the lock the second redeemer reads status="redeemed" and is correctly told
    # the gift is already used.
    from core.i18n import t

    locale = user.language_code or "ru"
    gift = await session.scalar(
        select(Gift).where(Gift.code == norm).with_for_update()
    )
    if gift is None:
        return False, t("gift.not_found", locale)
    if gift.status == "redeemed":
        return False, t("gift.already_used", locale)
    if gift.buyer_id == user.user_id:
        return False, t("gift.own_gift", locale)

    tx_id = f"gift:{norm}"
    # FIX: R12 - check the return value of each billing.* call. They return False when
    # the gift's gateway_tx_id was already processed (a duplicate redemption under a
    # DIFFERENT gift code that happened to collide, or a retry). In that case the gift
    # must NOT be marked "redeemed" — the buyer keeps their code and the recipient got
    # nothing, which is the honest state. Without this, mark "redeemed" on a no-op
    # left the buyer's code dead with no entitlement granted.
    if gift.kind == "sub":
        ok = await billing.activate_subscription(
            session, user, product=gift.product, months=gift.months or 1,
            gateway="gift", amount=0, gateway_tx_id=tx_id,
        )
        if not ok:
            return False, t("gift.already_used", locale)
        human = t("gift.redeemed_sub", locale, product=gift.product, months=gift.months or 1)
    elif gift.kind == "pack":
        ok = await billing.add_pack_credits(
            session, user, pack=gift.product, qty=gift.qty or 0,
            gateway="gift", amount=0, gateway_tx_id=tx_id,
        )
        if not ok:
            return False, t("gift.already_used", locale)
        human = t("gift.redeemed_pack", locale, product=gift.product, qty=gift.qty or 0)
    elif gift.kind == "credits":
        ok = await billing.add_credits(
            session, user, qty=gift.qty or 0,
            gateway="gift", amount=0, gateway_tx_id=tx_id,
        )
        if not ok:
            return False, t("gift.already_used", locale)
        human = t("gift.redeemed_credits", locale, qty=gift.qty or 0)
    else:
        return False, t("gift.unknown_kind", locale)

    gift.status = "redeemed"
    gift.redeemed_by = user.user_id
    gift.redeemed_at = datetime.now(UTC)
    await session.commit()
    return True, human
