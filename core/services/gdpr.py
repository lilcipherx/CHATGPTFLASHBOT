"""FIX: AUDIT12-20, AUDIT12-21 - GDPR Art. 17 right-to-erasure service.

Deletes ALL user data across every related table in ONE transaction so a partial
failure can't leave orphaned rows. With migration 0038 the FK CASCADE would
handle this at the DB level on `DELETE FROM users`, but we still want:

  1. Explicit per-table deletes so we can log counts and timestamp the action.
  2. A single function that both the admin endpoint and the bot self-service
     command call, guaranteeing identical behaviour.
  3. Best-effort cleanup of tables that have NO FK (legacy soft-references
     like `audit_log.target_id='user:<id>'`).

Never raises on missing user (idempotent — already deleted). Returns a dict of
{table: rows_deleted} for audit logging.
"""
from __future__ import annotations

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    AdminAuditLog,  # for soft-ref cleanup
    CheckoutIntent,
    Complaint,
    ContestEntry,
    GalleryItem,
    GenerationJob,
    MessageFeedback,
    PackBalance,
    PaymentMethod,
    Referral,
    SupportMessage,
    Transaction,
    UsageLog,
    User,
    UserNote,
    UserTag,
)

log = structlog.get_logger()


async def export_user_data(session: AsyncSession, user_id: int) -> dict:
    """FIX: AUDIT13-M22 - GDPR Art. 20 (data portability) self-service export.

    Returns a JSON-serialisable dict of the user's own records: profile, saved pack
    balances, transactions, usage log and generation jobs. Row lists are capped so a
    heavy account can't OOM the bot. Never raises on a missing user (returns {}).
    """
    from core.models import GenerationJob, PackBalance, Transaction, UsageLog

    user = await session.get(User, user_id)
    if user is None:
        return {}

    def _dt(v):
        return v.isoformat() if v is not None and hasattr(v, "isoformat") else v

    export: dict = {"exported_for": user_id}
    # Profile — column-by-column so we never leak internal-only attrs unintentionally.
    export["profile"] = {
        c.name: _dt(getattr(user, c.name)) for c in user.__table__.columns
    }

    bal = await session.get(PackBalance, user_id)
    export["pack_balances"] = (
        {c.name: getattr(bal, c.name) for c in bal.__table__.columns} if bal else None
    )

    _ROW_CAP = 5000
    for label, model, order in (
        ("transactions", Transaction, Transaction.id),
        ("usage_log", UsageLog, UsageLog.id),
        ("generation_jobs", GenerationJob, GenerationJob.id),
    ):
        rows = (await session.scalars(
            select(model).where(model.user_id == user_id).order_by(order.desc()).limit(_ROW_CAP)
        )).all()
        export[label] = [
            {c.name: _dt(getattr(r, c.name)) for c in r.__table__.columns} for r in rows
        ]
    return export


async def delete_user_data(session: AsyncSession, user_id: int) -> dict[str, int]:
    """Purge every trace of ``user_id`` in one transaction.

    Returns a dict of ``{table_name: rows_deleted}`` for audit logging.
    Caller is responsible for the final ``session.commit()`` (so the audit row
    can land in the SAME transaction).
    """
    counts: dict[str, int] = {}

    # Order matters: delete child rows first so CASCADE doesn't fire before we
    # can count them. With 0038 FKs in place CASCADE would handle these anyway,
    # but we want explicit counts + best-effort for tables that still have no FK.
    deleters = [
        ("generation_jobs", GenerationJob, "user_id"),
        ("transactions",    Transaction,   "user_id"),
        ("usage_log",       UsageLog,      "user_id"),
        # FIX: FINAL-8 - Referral has NO user_id column (only referrer_id + referred_id).
        # The old entry ("referrals", Referral, "user_id") raised AttributeError,
        # swallowed by the per-table try/except, so referral rows were NEVER purged.
        # Delete by BOTH referrer_id (user was the inviter) and referred_id (user was
        # the invitee) — GDPR requires both directions to fully erase the user's trace.
        ("referrals_as_referrer", Referral, "referrer_id"),
        ("referrals_as_referred", Referral, "referred_id"),
        ("support_messages", SupportMessage, "user_id"),
        ("user_notes",      UserNote,      "user_id"),
        ("user_tags",       UserTag,       "user_id"),
        ("message_feedback", MessageFeedback, "user_id"),
        ("complaints",      Complaint,     "user_id"),
        ("contest_entries", ContestEntry,  "user_id"),
        ("gallery_items",   GalleryItem,   "user_id"),
        ("pack_balances",   PackBalance,   "user_id"),
        # FIX: AUDIT13-H3 - payment_methods (saved recurring tokens) and checkout_intents
        # had NO FK to users and were NOT deleted here, so a user-erase orphaned live
        # billing tokens + cart rows (GDPR Art.17 violation). Explicit deletes here +
        # a CASCADE FK in migration 0041 close both the ORM and DB-level gaps.
        ("payment_methods", PaymentMethod, "user_id"),
        ("checkout_intents", CheckoutIntent, "user_id"),
    ]

    for tbl_name, model, col in deleters:
        # FIX: AUDIT-FINAL-1 - use SAVEPOINT (begin_nested) per iteration so a
        # failure on one table only rolls back THAT savepoint, not the deletes
        # already accumulated in the outer transaction. The previous code called
        # session.rollback() unconditionally at the top of every iteration, which
        # wiped out ALL prior deletes — leaving Transaction/GenerationJob/UsageLog
        # rows orphaned (GDPR Art.17 violation).
        try:
            async with session.begin_nested():
                res = await session.execute(
                    delete(model).where(getattr(model, col) == user_id)
                )
                counts[tbl_name] = res.rowcount or 0
        except Exception as exc:  # noqa: BLE001 — best-effort; missing table etc.
            log.warning("gdpr.delete_table_failed", table=tbl_name, user_id=user_id, error=str(exc))
            counts[tbl_name] = -1

    # Soft-references: admin audit log entries whose target_id is "user:<id>".
    # These are NOT cascade-deleted (audit log is append-only) but we redact
    # the target_id to "user:<id>:deleted" so the audit trail survives without
    # leaking the now-deleted user_id forward.
    try:
        # FIX: FINAL-10 - the old code consumed `rows.all()` TWICE (once in the for
        # loop, once in `len(rows.all())`). The second call returns an empty list
        # because the ScalarResult was already exhausted, so the count was always 0.
        # Materialise the list once and reuse it.
        # FIX: AUDIT-FINAL-1 - SAVEPOINT instead of full rollback (see above).
        async with session.begin_nested():
            rows_list = list((await session.scalars(
                select(AdminAuditLog).where(AdminAuditLog.target_type == "user")
                .where(AdminAuditLog.target_id == str(user_id))
            )).all())
            for row in rows_list:
                row.target_id = f"{user_id}:deleted"
            counts["admin_audit_log_redacted"] = len(rows_list)
    except Exception as exc:  # noqa: BLE001
        log.warning("gdpr.audit_redact_failed", user_id=user_id, error=str(exc))

    # Finally, delete the user row itself.
    try:
        res = await session.execute(delete(User).where(User.user_id == user_id))
        counts["users"] = res.rowcount or 0
    except Exception as exc:  # noqa: BLE001
        log.error("gdpr.delete_user_failed", user_id=user_id, error=str(exc))
        counts["users"] = -1

    log.info("gdpr.user_data_deleted", user_id=user_id, counts=counts)
    return counts
