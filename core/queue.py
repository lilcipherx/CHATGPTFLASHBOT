"""ARQ queue access from the bot process (enqueue async generation jobs)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings

_pool: ArqRedis | None = None

# Premium queue priority (ТЗ §8). ARQ pops jobs from its Redis sorted set in score
# (defer-time) order, so back-dating a job's ``_defer_until`` makes it sort ahead of
# everything enqueued at "now". The offset is deliberately huge (~10y) so a Premium
# job ALWAYS precedes any free job regardless of backlog age, while Premium jobs keep
# FIFO order among themselves (each is back-dated from its own enqueue time).
_PRIORITY_OFFSET = timedelta(days=3650)


class QueueUnavailable(Exception):
    """The job queue (Redis/ARQ) could not accept the job."""


async def get_queue() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def enqueue(function: str, *args, priority: bool = False) -> None:
    pool = await get_queue()
    if priority:
        # Back-date the score so this job jumps ahead of normal-priority jobs.
        await pool.enqueue_job(
            function, *args, _defer_until=datetime.now(UTC) - _PRIORITY_OFFSET
        )
    else:
        await pool.enqueue_job(function, *args)


async def is_priority_job(session: AsyncSession, job) -> bool:
    """True when ``job``'s owner is Premium AND admin-enabled queue priority is on
    (ТЗ §8). Best-effort: any lookup/config failure degrades to no priority, never
    blocks the enqueue."""
    try:
        from core.models import User
        from core.services import pricing

        if not await pricing.queue_priority_enabled(session):
            return False
        user = await session.get(User, job.user_id)
        return bool(user and user.is_premium)
    except Exception as exc:  # noqa: BLE001 — FIX: F34 - log so Premium users silently
        # losing queue priority is observable (was bare `return False` with no signal).
        # Priority is still best-effort: never block the enqueue.
        import structlog
        structlog.get_logger().warning("queue.priority_check_failed", error=str(exc))
        return False


async def enqueue_or_refund(session: AsyncSession, job, worker: str) -> None:
    """Enqueue ``job`` for ``worker``; if the queue is unavailable, mark the job
    failed, refund whatever was charged, and raise QueueUnavailable so the caller
    can tell the user to retry instead of leaving the charge with a stuck job.

    Premium-owned jobs are enqueued with priority (ТЗ §8) when admin-enabled."""
    try:
        await enqueue(worker, str(job.job_id), priority=await is_priority_job(session, job))
    except Exception as exc:  # noqa: BLE001 — queue/Redis down
        from core.services.refunds import refund_job

        job.status = "failed"
        job.error = f"queue unavailable: {exc}"
        # FIX: AUDIT-5 - wrap refund_job in try/except so QueueUnavailable is always raised
        try:
            await refund_job(session, job)
        except Exception as refund_err:  # noqa: BLE001
            import structlog
            structlog.get_logger().error(
                'queue.refund_failed', job_id=str(job.job_id), error=str(refund_err))
        await session.commit()
        raise QueueUnavailable() from exc
