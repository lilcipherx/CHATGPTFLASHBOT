"""Premium auto-renewal (ТЗ §6) — selection + recurring charge orchestration.

Picks the premium users who opted in (``User.auto_renew``) and whose subscription
is about to lapse, then attempts a real recurring charge for each against the
payment method they vaulted at their last subscription checkout.

The charge runs off-session against a saved token (YooKassa ``payment_method_id``
or Stripe customer + ``payment_method``, captured in ``core.payments`` and stored
by ``core.services.payment_methods``). A user with no saved method (e.g. their last
purchase was via Stars / СБП / Crypto, which have no off-session charge) is left
for normal manual re-subscription. On a successful charge the subscription is
extended via the idempotent ``billing.activate_subscription``; on a decline nothing
is extended. :func:`attempt_renewal` returns ``"renewed"`` | ``"no_payment_method"``
| ``"failed"``.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionFactory
from core.models import User
from core.timeutils import ensure_aware

log = logging.getLogger(__name__)

# How long after expiry we still consider a sub renewable. A renewal cron that
# runs daily can legitimately pick up a sub that lapsed a few hours ago (e.g. it
# expired overnight before the 03:00 run); beyond this grace we treat it as fully
# lapsed and leave it to normal re-subscription rather than auto-charging.
RENEWAL_GRACE_HOURS = 48


async def due_for_renewal(session: AsyncSession, within_hours: int = 24) -> list[User]:
    """Premium users who opted into auto-renewal and whose subscription is due.

    "Due" = ``auto_renew`` is True, the user has an active tier + expiry, and
    ``sub_expires`` falls inside the window ``[now - RENEWAL_GRACE_HOURS,
    now + within_hours]`` — i.e. expiring soon, or only just lapsed (within the
    grace). Far-future expiries and non-opted-in users are excluded.
    """
    now = datetime.now(UTC)
    upper = now + timedelta(hours=within_hours)
    lower = now - timedelta(hours=RENEWAL_GRACE_HOURS)

    rows = (
        await session.scalars(
            select(User).where(
                User.auto_renew.is_(True),
                User.sub_tier.is_not(None),
                User.sub_expires.is_not(None),
            )
        )
    ).all()

    # Window-filter in Python so the naive/aware normalisation (SQLite) is applied
    # consistently; the auto_renew=True set is tiny, so this is cheap.
    return [u for u in rows if lower <= ensure_aware(u.sub_expires) <= upper]


async def attempt_renewal(session: AsyncSession, user: User) -> str:
    """Recurringly charge ``user`` for one more Premium month against their saved
    payment method, extending the subscription on success.

    Returns ``"no_payment_method"`` (no vaulted token — nothing charged, sub
    untouched), ``"failed"`` (gateway declined / misconfigured price — sub
    untouched), or ``"renewed"`` (charged + extended). Function-local imports avoid
    a payments↔services import cycle.
    """
    from core.constants import SUBSCRIPTION_PRICES
    from core.payments import PaymentError
    from core.payments.service import charge_saved_method, stars_to_minor
    from core.services import payment_methods, pricing
    from core.services.billing import activate_subscription

    method = await payment_methods.get_method(session, user.user_id)
    if method is None:
        log.info(
            "autorenew: no saved payment method for user_id=%s (sub NOT extended)",
            user.user_id,
        )
        return "no_payment_method"

    # Renew at the live one-month price for the user's current tier (admin-editable,
    # incl. any active sale), falling back to the static catalogue if unset.
    tier = user.sub_tier or "premium"
    stars = await pricing.subscription_price(session, tier, 1)
    if not stars:
        stars = SUBSCRIPTION_PRICES.get(tier, {}).get(1)
    if not stars:
        log.warning("autorenew: no price for tier=%s user_id=%s", tier, user.user_id)
        return "failed"

    minor, currency = stars_to_minor(stars, method.gateway)
    # Same payload shape checkout uses (sub:<uid>:<tier>:<months>:<quoted_minor>) so
    # the renewal transaction is indistinguishable from a normal purchase downstream.
    payload = f"sub:{user.user_id}:{tier}:1:{minor}"
    # Deterministic idempotency key tied to THIS renewal (the expiry being renewed):
    # if the charge succeeds but the local sub-extension doesn't commit (crash), the
    # next sweep re-attempts with the SAME key while sub_expires is unchanged, so the
    # gateway dedupes instead of charging the user twice. A successful renewal moves
    # sub_expires forward, yielding a fresh key for the next period.
    idem = f"renew:{user.user_id}:{int(ensure_aware(user.sub_expires).timestamp())}"
    try:
        tx_id = await charge_saved_method(
            method, amount=minor, currency=currency,
            description=f"Premium {tier} auto-renewal", payload=payload,
            idempotency_key=idem,
        )
    except PaymentError as exc:
        log.warning("autorenew: charge declined user_id=%s: %s", user.user_id, exc)
        # FIX: AUDIT-11 - deactivate the saved method so cron stops retrying a dead card
        try:
            await payment_methods.deactivate(session, method)
            await session.commit()
        except Exception:
            log.warning("autorenew: deactivate failed user_id=%s", user.user_id)
        return "failed"
    if not tx_id:
        # Gateway has no off-session charge support — treat as nothing to renew.
        # FIX: AUDIT-11 - also deactivate when gateway returned no tx_id
        try:
            await payment_methods.deactivate(session, method)
            await session.commit()
        except Exception:
            log.warning("autorenew: deactivate failed user_id=%s", user.user_id)
        return "failed"

    # FIX: AUDIT12-3 - if activate_subscription raises AFTER charge, ACTUALLY call
    # the gateway refund (was: import without call → user charged, no sub, no refund).
    try:
        ok = await activate_subscription(
            session, user, product=tier, months=1,
            gateway=method.gateway, amount=minor, gateway_tx_id=tx_id,
        )
    except Exception as exc:
        log.error(
            "autorenew: activate_subscription failed user_id=%s: %s — refunding",
            user.user_id, exc,
        )
        # FIX: AUDIT-P2 (P0) - snapshot every scalar the refund path needs BEFORE
        # session.rollback(). rollback() expires all ORM attributes; under AsyncSession
        # a later synchronous read of an expired attribute (method.gateway, user.*)
        # raises MissingGreenlet, which previously either got swallowed by the inner
        # except or propagated out of its log call — either way the money-back refund
        # silently never ran, leaving the user charged with no subscription.
        gateway = method.gateway
        uid = user.user_id
        locale = getattr(user, "language_code", "ru") or "ru"
        try:
            await session.rollback()
            from core.payments import get_provider
            from core.services.refunds import refund_stars
            if gateway == "stars":
                await refund_stars(
                    session, uid, product=f"sub:{tier}", charge_id=tx_id, locale=locale
                )
            else:
                gw = get_provider(gateway)
                if gw is not None and hasattr(gw, "refund"):
                    await gw.refund(gateway_tx_id=tx_id, amount=minor)
            await session.commit()
        except Exception as refund_exc:  # noqa: BLE001
            log.error("autorenew: refund_after_activate_failed user_id=%s: %s", uid, refund_exc)
        return "failed"
    return "renewed" if ok else "failed"


async def run_autorenew(session: AsyncSession | None = None) -> dict[str, int]:
    """Select due users and attempt a renewal charge for each.

    Returns counts ``{"due": N, "renewed": N, "skipped": N}`` where ``skipped``
    is every user whose renewal did not succeed — either no vaulted payment method
    (Stars/СБП/Crypto checkouts leave none) or a declined/misconfigured charge. A sub
    is only ever extended after a real successful charge. Opens its own session if
    none is passed.
    """
    if session is None:
        async with SessionFactory() as own:
            return await run_autorenew(own)

    users = await due_for_renewal(session)
    # FIX: AUDIT-P4 (P1) - snapshot the ids while attributes are fresh, then re-load
    # each user per iteration. A prior user's renewal can roll back the shared session
    # (decline/refund paths), which expires EVERY loaded User; iterating over the stale
    # objects would hit MissingGreenlet on the next user's expired attribute and abort
    # the whole sweep. session.get() re-fetches through the async greenlet safely.
    user_ids = [u.user_id for u in users]
    renewed = 0
    for uid in user_ids:
        # FIX: AUDIT-11 - per-user try/except so one failure doesn't block others
        try:
            user = await session.get(User, uid)
            if user is None:
                continue
            result = await attempt_renewal(session, user)
            if result == "renewed":
                renewed += 1
        except Exception as exc:
            log.warning("autorenew: user %s failed: %s", uid, exc)
            await session.rollback()
    await session.commit()

    return {"due": len(user_ids), "renewed": renewed, "skipped": len(user_ids) - renewed}
