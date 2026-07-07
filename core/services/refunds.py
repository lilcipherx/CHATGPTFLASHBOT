"""Canonical refund for a GenerationJob's charge.

Single source of truth for "give back whatever a job charged" so the bot
handlers, the Mini App API and the workers all reverse a charge the same way:
🪙 credits, an image/video/music pack credit, a free weekly Mini App slot, or a
Telegram Stars purchase (one-time services like avatar that record no pack/credit
on the job — the charge lives in the transactions ledger).

Each underlying grant/refund commits, so calling this leaves the session clean.
"""
from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

# Generation services paid with Telegram Stars (no pack/credit on the job — the
# charge is a transactions-ledger row keyed on product == service). The stuck-job
# sweep is the only blind caller that picks these up, so refund_job must cover
# them or a swept Stars job leaves the user charged with nothing.
_STARS_SERVICES = {"avatar"}


async def refund_stars(
    session: AsyncSession, user_id: int, product: str,
    charge_id: str | None = None, locale: str = "ru",
) -> bool:
    """Refund a Stars purchase end to end: find the refundable charge (the EXACT
    ``charge_id`` if given — the tx this job paid for — else the newest of ``product``),
    issue the REAL Telegram refund FIRST, then mark the ledger refunded and notify.
    Returns True iff the money refund succeeded.

    Money-before-ledger: if ``bot.refund_star_payment`` fails, the tx is left ``paid``
    (accurate — the user is still owed) instead of a false ``refunded``, so manual
    reconciliation or a retry can re-issue it. Idempotent across the per-service worker
    and the stuck-job sweep via ``mark_stars_refunded`` (paid→refunded at most once)."""
    from core.bot_client import get_bot
    from core.i18n import t
    from core.services.billing import mark_stars_refunded, peek_refundable_stars_tx

    # FIX: AUDIT-5 - lock the Transaction row BEFORE peek+refund to prevent
    # concurrent double-refund race (worker + stuck-job sweep)
    from sqlalchemy import select
    from core.models import Transaction
    cid = await peek_refundable_stars_tx(session, user_id, product, charge_id)
    if not cid:
        return False  # nothing paid to refund (or already refunded — idempotent no-op)
    # Lock the tx row for the duration of the money-refund call
    await session.execute(
        select(Transaction).where(Transaction.gateway_tx_id == cid).with_for_update()
    )
    bot = get_bot()
    try:
        await bot.refund_star_payment(user_id=user_id, telegram_payment_charge_id=cid)
    except Exception:  # noqa: BLE001 — leave the tx 'paid' for reconciliation / retry
        log.error("refund.stars_money_failed", user_id=user_id, charge_id=cid)
        return False
    # Money is back → now (and only now) reverse the entitlement + mark the ledger.
    # FIX: R5 - if mark_stars_refunded raises (e.g. DB hiccup mid-reversal), the user's
    # money is already back at Telegram but our ledger still says "paid". Log + return
    # False so the caller (worker / sweep) re-tries mark_stars_refunded on the next
    # tick instead of silently swallowing the inconsistency.
    ledger_reversed = False
    try:
        ledger_reversed = await mark_stars_refunded(session, cid)
    except Exception:  # noqa: BLE001 — ledger reversal failed AFTER the money refund
        log.error(
            "refund.stars_ledger_failed", user_id=user_id, charge_id=cid,
            error="mark_stars_refunded raised; money already returned to the user, "
                  "ledger must be reconciled manually or on the next sweep",
        )
        return False
    # FIX: L6 - only DM the user if THIS call actually performed the reversal (was: DM
    # sent even on a retry where mark_stars_refunded returned False → duplicate DM).
    if ledger_reversed:
        try:
            await bot.send_message(user_id, t("refund.stars", locale))
        except Exception:  # noqa: BLE001 — the notice is best-effort, the refund stands
            pass
    return True


async def refund_job(session: AsyncSession, job) -> None:
    """Reverse the charge recorded on ``job`` (no-op if nothing was charged).

    Idempotent at the row for credits / packs / free-slot charges: the reversal is
    gated on a conditional UPDATE that stamps ``refunded_at`` only while it is still
    NULL. The first call wins the claim and performs the reversal; any later or
    concurrent call sees rowcount 0 and returns without touching a balance — so the
    charge comes back at most once even if several paths (worker fail, stuck-job
    sweep, admin cancel, enqueue-fail) race or repeat. The claim is flushed in the
    same transaction as the grant below, so if the grant raises before commit the
    claim rolls back with it.

    Stars-paid services (avatar) are idempotent at the LEDGER instead (tx paid→refunded)
    and do NOT stamp ``refunded_at``: the money-first ``refund_stars`` must be able to
    leave the tx ``paid`` (retryable) on a transient bot failure without a refunded_at
    stamp wrongly blocking the retry. So the stars branch is handled before the claim.

    The row is claimed only when something was actually charged, so a no-charge job
    (free trial that cost nothing, or an unrecognised shape) never burns the slot.
    """
    from datetime import UTC, datetime

    from sqlalchemy import update

    from core.models import GenerationJob, User
    from core.services import credits, packs
    from core.services.quota import refund_miniapp, refund_sponsored

    # Decide what (if anything) was charged BEFORE claiming, so a job with nothing to
    # reverse leaves refunded_at NULL (an unmapped charge shape stays reversible
    # rather than being silently marked refunded).
    if job.pack_type == "credits" and job.cost_credits:
        reverse = "credits"
    elif job.pack_type in ("image", "video", "music") and job.cost_credits:
        reverse = "pack"
    elif (job.params or {}).get("sponsored_free"):
        reverse = "sponsored"
    elif (job.params or {}).get("free"):
        reverse = "free"
    elif job.service in _STARS_SERVICES:
        reverse = "stars"
    else:
        return  # nothing was charged — nothing to reverse

    if reverse == "stars":
        # Refund the EXACT tx this job paid for (charge id stored on the job), money
        # first. Idempotency is the ledger tx status, not refunded_at, so don't claim.
        from core.services.users import user_locale

        locale = await user_locale(session, job.user_id)
        ok = await refund_stars(
            session, job.user_id, job.service,
            charge_id=(job.params or {}).get("charge_id"), locale=locale,
        )
        # FIX: AUDIT-5 - stamp refunded_at on job after successful Stars refund
        # so the stuck-job sweep stops re-picking this job on every run.
        if ok:
            from datetime import UTC, datetime
            from sqlalchemy import update
            from core.models import GenerationJob
            await session.execute(
                update(GenerationJob)
                .where(GenerationJob.job_id == job.job_id, GenerationJob.refunded_at.is_(None))
                .values(refunded_at=datetime.now(UTC))
            )
            await session.commit()
        return

    claimed = await session.execute(
        update(GenerationJob)
        .where(GenerationJob.job_id == job.job_id, GenerationJob.refunded_at.is_(None))
        .values(refunded_at=datetime.now(UTC))
    )
    if claimed.rowcount == 0:
        # Already refunded by a prior or concurrent call — never reverse a charge twice.
        return

    if reverse == "credits":
        user = await session.get(User, job.user_id)
        if user:
            await credits.grant(session, user, job.cost_credits)
    elif reverse == "pack":
        await packs.refund(session, job.user_id, job.pack_type, job.cost_credits)
    elif reverse == "free":
        user = await session.get(User, job.user_id)
        if user:
            await refund_miniapp(session, user)
    elif reverse == "sponsored":
        user = await session.get(User, job.user_id)
        if user:
            await refund_sponsored(session, user)
