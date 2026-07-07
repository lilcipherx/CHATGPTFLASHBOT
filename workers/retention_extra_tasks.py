"""FIX: AUDIT12-M5 - additional retention sweeps for compliance tables.

The existing prune_results handles generation/gallery artifacts. This module
adds purges for:
  - AdminAuditLog older than 365 days (compliance: keep 1y of audit history).
  - Transaction rows older than 7 years (tax/accounting requirement).
  - SupportMessage rows older than 1 year (support SLA).
  - UserNote, UserTag: keep indefinitely (active CRM data).

Each purge is bounded to 50k rows per run to avoid long-running transactions.
"""
import structlog
from datetime import UTC, datetime, timedelta
from sqlalchemy import delete, select
from core.db import SessionFactory
from core.models import AdminAuditLog, SupportMessage, Transaction

log = structlog.get_logger()
BATCH = 50_000

# FIX: AUDIT12-M5 - the module docstring promises "bounded to 50k rows per run";
# without an explicit LIMIT a bulk DELETE would scan+lock every matching row in
# one transaction (multi-year audit logs / transactions tables can easily exceed
# a million rows, which would bloat WAL / hold locks long enough to trip the cron
# timeout). Each purge below selects up to BATCH ids in a subquery and DELETEs
# only those — the next daily tick picks up the remainder. Idempotent +
# restartable: a partial run leaves the DB consistent and the next run continues.


async def purge_old_audit_logs(ctx) -> None:
    cutoff = datetime.now(UTC) - timedelta(days=365)
    async with SessionFactory() as session:
        res = await session.execute(
            delete(AdminAuditLog).where(AdminAuditLog.id.in_(
                select(AdminAuditLog.id)
                .where(AdminAuditLog.created_at < cutoff)
                .limit(BATCH)
            ))
        )
        if res.rowcount:
            log.info("retention.audit_logs_purged", count=res.rowcount)
        await session.commit()


async def purge_old_transactions(ctx) -> None:
    cutoff = datetime.now(UTC) - timedelta(days=365 * 7)
    async with SessionFactory() as session:
        res = await session.execute(
            delete(Transaction).where(Transaction.tx_id.in_(
                select(Transaction.tx_id)
                .where(Transaction.created_at < cutoff)
                .limit(BATCH)
            ))
        )
        if res.rowcount:
            log.info("retention.transactions_purged", count=res.rowcount)
        await session.commit()


async def purge_old_support_messages(ctx) -> None:
    cutoff = datetime.now(UTC) - timedelta(days=365)
    async with SessionFactory() as session:
        res = await session.execute(
            delete(SupportMessage).where(SupportMessage.id.in_(
                select(SupportMessage.id)
                .where(SupportMessage.created_at < cutoff)
                .limit(BATCH)
            ))
        )
        if res.rowcount:
            log.info("retention.support_messages_purged", count=res.rowcount)
        await session.commit()
