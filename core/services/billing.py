"""Subscription / pack activation with idempotent transaction recording."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import PackBalance, Transaction, UsageLog, User
from core.payments.base import gateway_currency


async def _is_first_purchase(session: AsyncSession, user_id: int) -> bool:
    """True when the just-recorded paid tx is the user's only paid transaction.
    Flushes so the pending insert is counted deterministically."""
    await session.flush()
    n = await session.scalar(
        select(func.count()).select_from(Transaction)
        .where(Transaction.user_id == user_id, Transaction.status == "paid")
    )
    return n == 1


async def _apply_purchase_promos(
    session: AsyncSession, user: User, *, product: str, qty: int | None,
    # FIX: B2 - carry tx.id so revoke_entitlement can find the exact bonus log
    tx: Transaction | None = None,
) -> None:
    """Grant configured promo bonuses for a just-recorded paid purchase, folded into
    the caller's transaction (commit=False — the caller commits). Cashback applies to
    🪙 top-ups; a first-purchase bonus applies once on the first paid tx. Both default
    to 0 (off) and are admin-configurable via business_config. Best-effort: a config
    read failure must never break a real purchase.

    The bonus is added to ``user.credits`` IN PLACE (not via credits.grant) so it
    composes with the purchase's other pending mutations — credits.grant re-SELECTs
    the row (with_for_update) and would discard the just-applied, uncommitted grant /
    subscription change. The caller commits."""
    from core.services import pricing

    try:
        promo = await pricing.promos(session)
    except Exception:  # noqa: BLE001 — config unavailable -> no promo, purchase stands
        # FIX: AUDIT-6 - log promo config failure so ops can reconcile
        import structlog
        structlog.get_logger().warning("billing.promo_config_unavailable", user_id=user.user_id)
        return
    bonus = 0
    if product == "credits" and qty and promo["cashback_percent"] > 0:
        bonus += qty * promo["cashback_percent"] // 100
    if promo["first_purchase_bonus"] > 0 and await _is_first_purchase(session, user.user_id):
        bonus += promo["first_purchase_bonus"]
    if bonus > 0:
        # FIX: B10 - flush pending mutations (e.g. credits.grant) BEFORE refresh so
        # the re-read from DB includes them. Without flush, refresh() reads the stale
        # DB value (before the uncommitted grant) and discards the purchased credits.
        # Verified: SQLAlchemy 2.0.36 Session.refresh() does NOT auto-flush.
        await session.flush()
        await session.refresh(user, with_for_update=True)
        user.credits = max(0, user.credits + bonus)
        # Log the grant so the post-commit hook can DM the user about it (the bonus is
        # otherwise invisible — it just lands in the balance). Folded into the caller's
        # transaction, so it commits atomically with the purchase. `notified` is flipped
        # by notify_purchase_bonus to keep the DM one-shot.
        # FIX: B2 - store tx_id in meta so revoke_entitlement can find the EXACT
        # bonus log for this transaction (was: unscoped query picked the most-recent
        # bonus log → wrong reversal on multi-purchase users → money leak).
        _meta = {"amount": bonus, "notified": False}
        if tx is not None:
            _meta["tx_id"] = str(tx.tx_id)  # FIX: C1 - Transaction PK is tx_id, not id
        session.add(UsageLog(
            user_id=user.user_id, action="purchase_bonus",
            meta=_meta,
        ))


async def _record_tx(
    session: AsyncSession,
    *,
    user_id: int,
    product: str,
    gateway: str,
    amount: int,
    gateway_tx_id: str | None,
    duration_months: int | None = None,
    qty: int | None = None,
    credits_added: int | None = None,
) -> Transaction | None:
    """Insert a paid transaction. Returns None if this gateway_tx_id was already
    processed (idempotency guard for webhook retries)."""
    if gateway_tx_id:
        existing = await session.scalar(
            select(Transaction).where(Transaction.gateway_tx_id == gateway_tx_id)
        )
        if existing is not None:
            return None
    tx = Transaction(
        user_id=user_id,
        product=product,
        gateway=gateway,
        amount=amount,
        currency=gateway_currency(gateway),
        gateway_tx_id=gateway_tx_id,
        status="paid",
        duration_months=duration_months,
        qty=qty,
        credits_added=credits_added,
        paid_at=datetime.now(UTC),
    )
    if gateway_tx_id:
        # Add + flush INSIDE a SAVEPOINT so a concurrent webhook delivery that passed
        # the SELECT above trips the unique(gateway_tx_id) constraint here (not at the
        # caller's commit). FIX: AUDIT-6 / AUDIT-P3 - on conflict the savepoint rolls
        # back and cleanly discards `tx` (it was added within the savepoint), leaving
        # the caller's outer transaction usable. A bare flush() left the session
        # aborted, so every later statement in apply_event raised PendingRollbackError.
        # `tx` must be added inside the savepoint, else its rollback wouldn't remove it
        # and the caller's commit would re-INSERT and re-conflict. Matches the proven
        # pattern in referrals._grant_once.
        try:
            async with session.begin_nested():
                session.add(tx)
                await session.flush()
        except IntegrityError:
            return None
    else:
        session.add(tx)
    return tx


async def record_one_time(
    session: AsyncSession,
    user: User,
    *,
    product: str,
    gateway: str,
    amount: int,
    gateway_tx_id: str | None,
) -> bool:
    """Record a one-time purchase (e.g. avatar pack). Idempotent; returns False
    if this gateway_tx_id was already processed."""
    tx = await _record_tx(
        session,
        user_id=user.user_id,
        product=product,
        gateway=gateway,
        amount=amount,
        gateway_tx_id=gateway_tx_id,
    )
    if tx is None:
        return False
    # FIX: F6 - apply purchase promos (cashback / first-purchase bonus) on one-time
    # purchases too, so an avatar bought as the user's FIRST paid tx still grants the
    # first-purchase bonus. Without this, _is_first_purchase counted the avatar tx
    # (n==1) but no bonus was granted, and a later credits/pack/sub purchase saw n!=1
    # and never got the bonus either — bonus lost forever.
    # FIX: C3 - lock User row before _apply_purchase_promos so two concurrent one-time
    # purchases can't both pass _is_first_purchase and double-grant the bonus.
    await session.refresh(user, with_for_update=True)
    # FIX: B2 - pass tx
    await _apply_purchase_promos(session, user, product=product, qty=None, tx=tx)
    await session.commit()
    return True


async def activate_subscription(
    session: AsyncSession,
    user: User,
    *,
    product: str,
    months: int,
    gateway: str,
    amount: int,
    gateway_tx_id: str | None,
) -> bool:
    tx = await _record_tx(
        session,
        user_id=user.user_id,
        product=product,
        gateway=gateway,
        amount=amount,
        gateway_tx_id=gateway_tx_id,
        duration_months=months,
    )
    if tx is None:
        return False  # already processed

    # FIX: R1 - re-fetch the user row under FOR UPDATE so two concurrent webhook
    # activations for the SAME user (e.g. a duplicate delivery) can't both read the
    # same sub_expires and overwrite each other's extension (lost update). The unique
    # (gateway_tx_id) guard on _record_tx already prevents a double-grant for the SAME
    # tx, but two DIFFERENT txs (a sub + a renewal in the same minute) still race on
    # the user row. The lock serializes them so each stacks its months correctly.
    await session.refresh(user, with_for_update=True)
    now = datetime.now(UTC)
    current = user.sub_expires
    if current is not None and current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    base = current if (current and current > now) else now
    user.sub_tier = product
    user.sub_expires = base + timedelta(days=30 * months)
    # FIX: B2 - pass tx
    await _apply_purchase_promos(session, user, product=product, qty=None, tx=tx)
    await session.commit()
    return True


async def add_credits(
    session: AsyncSession,
    user: User,
    *,
    qty: int,
    gateway: str,
    amount: int,
    gateway_tx_id: str | None,
) -> bool:
    """Credit 🪙 credits after a paid top-up. Idempotent on gateway_tx_id."""
    from core.services import credits

    tx = await _record_tx(
        session, user_id=user.user_id, product="credits", gateway=gateway,
        amount=amount, gateway_tx_id=gateway_tx_id, qty=qty, credits_added=qty,
    )
    if tx is None:
        return False
    await credits.grant(session, user, qty, commit=False)
    # FIX: B2 - pass tx
    await _apply_purchase_promos(session, user, product="credits", qty=qty, tx=tx)
    await session.commit()
    return True


PACK_FIELD = {
    "image_pack": "image_credits",
    "video_pack": "video_credits",
    "music_pack": "music_credits",
}


async def add_pack_credits(
    session: AsyncSession,
    user: User,
    *,
    pack: str,
    qty: int,
    gateway: str,
    amount: int,
    gateway_tx_id: str | None,
) -> bool:
    tx = await _record_tx(
        session,
        user_id=user.user_id,
        product=pack,
        gateway=gateway,
        amount=amount,
        gateway_tx_id=gateway_tx_id,
        qty=qty,
        credits_added=qty,
    )
    if tx is None:
        return False

    # FIX: R2+M2 - lock the PackBalance row with refresh (not stale identity-map get).
    # FIX: #7 - guard against IntegrityError on first-time PackBalance insert race
    # (two concurrent first-time pack purchases both get None, both INSERT).
    balances = await session.get(PackBalance, user.user_id)
    if balances is None:
        balances = PackBalance(user_id=user.user_id)
        session.add(balances)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            balances = await session.get(PackBalance, user.user_id)
            if balances is None:
                raise  # not a PK race — surface the real error
            # Re-record the tx since rollback discarded it
            tx = await _record_tx(
                session, user_id=user.user_id, product=pack, gateway=gateway,
                amount=amount, gateway_tx_id=gateway_tx_id, qty=qty, credits_added=qty,
            )
            if tx is None:
                return False
    await session.refresh(balances, with_for_update=True)
    # FIX: AUDIT-M1 - lock the User row before _apply_purchase_promos so the
    # first-purchase-bonus check (_is_first_purchase) is serialized against a
    # concurrent first sub/credits purchase (which never touch PackBalance).
    # Mirrors the C3/R1 locks in record_one_time/activate_subscription.
    await session.refresh(user, with_for_update=True)
    field = PACK_FIELD[pack]
    setattr(balances, field, getattr(balances, field) + qty)
    await _apply_purchase_promos(session, user, product=pack, qty=None, tx=tx)  # FIX: B2 - pass tx
    await session.commit()
    return True


async def notify_purchase_bonus(session: AsyncSession, user: User) -> int:
    """Best-effort post-commit DM telling the buyer about the bonus ✨ their purchase
    just earned (cashback / first-purchase). Each ``purchase_bonus`` log is announced
    once (its ``notified`` flag is flipped). Returns the amount DM'd, or 0. Never
    raises into the payment path."""
    uid = user.user_id
    row = await session.scalar(
        select(UsageLog)
        .where(UsageLog.user_id == uid, UsageLog.action == "purchase_bonus")
        .order_by(UsageLog.id.desc()).limit(1)
    )
    if row is None or (row.meta or {}).get("notified"):
        return 0
    amount = int((row.meta or {}).get("amount", 0))
    if amount <= 0:
        return 0
    # FIX: AUDIT-6 - send DM FIRST, only flip notified=True after success
    try:
        from core.bot_client import get_bot
        from core.i18n import t
        from core.services.users import user_locale

        locale = await user_locale(session, uid)
        await get_bot().send_message(uid, t("promo.purchase_bonus", locale, amount=amount))
        row.meta = {**(row.meta or {}), "notified": True}  # one-shot guard (only on success)
        await session.commit()
    except Exception:  # noqa: BLE001 — notification is best-effort
        # Leave notified=False so next purchase re-attempts the DM
        import structlog
        structlog.get_logger().warning("billing.bonus_notify_failed", user_id=uid)
    return amount


async def peek_refundable_stars_tx(
    session: AsyncSession, user_id: int, product: str, charge_id: str | None = None
) -> str | None:
    """The telegram_payment_charge_id of the paid, non-refunded Stars purchase to
    refund — the EXACT tx ``charge_id`` if given (the one this job paid for), else the
    newest of ``product`` (back-compat for jobs/sweeps without a stored charge id).
    None when there's nothing to refund.

    Read-only on purpose: it mutates nothing, so the caller issues the real Stars money
    refund FIRST and marks the ledger only after it succeeds (mark_stars_refunded) —
    closing the 'ledger says refunded but the Stars were never returned' window."""
    q = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.gateway == "stars",
        Transaction.status == "paid",
    )
    q = q.where(Transaction.gateway_tx_id == charge_id) if charge_id \
        else q.where(Transaction.product == product)
    tx = await session.scalar(q.order_by(Transaction.created_at.desc()))
    return tx.gateway_tx_id if (tx and tx.gateway_tx_id) else None


async def mark_stars_refunded(session: AsyncSession, charge_id: str) -> bool:
    """Reverse the entitlement of the paid Stars tx with this ``charge_id`` and mark it
    refunded. Call ONLY after the actual Stars money refund (bot.refund_star_payment)
    has succeeded. Idempotent: a tx already refunded (or unknown) is a no-op → False,
    so the money refund + entitlement reversal happen at most once even if the worker
    and the stuck-job sweep both reach it."""
    # with_for_update: the docstring's "worker AND stuck-job sweep both reach it"
    # is a real concurrent path. Without the row lock both callers could read the
    # tx as still `paid`, each run revoke_entitlement, and double-reverse the grant
    # (credits clamp at 0, but premium months would be subtracted twice). The lock
    # serializes them so the second waits, re-reads `refunded`, and no-ops. No-op on
    # SQLite (which serializes writes anyway); a real row lock on Postgres.
    tx = await session.scalar(
        select(Transaction).where(
            Transaction.gateway_tx_id == charge_id,
            Transaction.gateway == "stars",
            Transaction.status == "paid",
        ).with_for_update()
    )
    if tx is None:
        return False
    await revoke_entitlement(session, tx)
    tx.status = "refunded"
    await session.commit()
    return True


async def revoke_entitlement(session: AsyncSession, tx: Transaction) -> None:
    """Reverse whatever a paid transaction granted (called on admin refund), so a
    refunded user no longer keeps the premium/packs/credits. Clamps to >=0 and
    never raises on missing data. Mutates only — the CALLER commits (so the status
    change and the reversal land in one transaction). Does NOT touch the gateway
    (money) — that is a separate, gateway-specific refund call."""
    # FIX: R3+M2 - lock User row with refresh (not stale identity-map get).
    user = await session.get(User, tx.user_id)
    if user is None:
        return
    await session.refresh(user, with_for_update=True)
    product = tx.product
    granted = tx.credits_added or tx.qty or 0

    if product in ("premium", "premium_x2"):
        months = tx.duration_months or 0
        exp = user.sub_expires
        if exp is not None:
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            new_exp = exp - timedelta(days=30 * months)
            if new_exp <= datetime.now(UTC):
                user.sub_tier = None
                user.sub_expires = None
            else:
                user.sub_expires = new_exp
    elif product in PACK_FIELD:  # image_pack | video_pack | music_pack
        # FIX: M2 - refresh under lock instead of stale identity-map get.
        balances = await session.get(PackBalance, user.user_id)
        if balances is not None:
            await session.refresh(balances, with_for_update=True)
            field = PACK_FIELD[product]
            setattr(balances, field, max(0, getattr(balances, field) - granted))
    elif product == "credits":
        user.credits = max(0, user.credits - granted)
    # FIX: B3 - bonus reversal runs for ALL products (not just credits), because
    # _apply_purchase_promos grants the first-purchase bonus as user.credits for ANY
    # product (subs/packs/avatars/credits). The old code only reversed it inside the
    # `elif product == "credits":` branch, so refunding a sub/pack/avatar that carried
    # a first-purchase bonus left the bonus in place → refund→re-purchase cycle
    # re-granted it each time (money leak).
    # FIX: B2 - query scoped by tx_id (stored in meta by _apply_purchase_promos) so the
    # EXACT bonus log for THIS transaction is reversed, not the most-recent one.
    try:
        bonus_log = await session.scalar(
            select(UsageLog).where(
                UsageLog.user_id == user.user_id,
                UsageLog.action == "purchase_bonus",
                UsageLog.meta["tx_id"].as_string() == str(tx.tx_id),  # FIX: C2
            ).limit(1)
        )
        if bonus_log is not None:
            bonus_amount = int((bonus_log.meta or {}).get("amount", 0))
            already_reversed = bool((bonus_log.meta or {}).get("reversed"))
            if bonus_amount > 0 and not already_reversed:
                user.credits = max(0, user.credits - bonus_amount)
                bonus_log.meta = {**(bonus_log.meta or {}), "reversed": True}
    except Exception:  # noqa: BLE001 — bonus reversal is best-effort
        # FIX: AUDIT-6 - log bonus reversal failure so admin can reconcile
        import structlog
        structlog.get_logger().warning(
            "billing.bonus_reversal_failed", user_id=user.user_id, tx_id=tx.tx_id)
    # "avatar" and other one-time services have nothing to reverse.
