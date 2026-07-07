"""Cron tasks: weekly quota reset, subscription expiry, stuck-job sweep (§8)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from arq import cron
from sqlalchemy import or_, select, update

from core.config import settings
from core.db import SessionFactory
from core.models import GenerationJob, User
from core.services.refunds import refund_job

# A generation job stuck this long was almost certainly abandoned by a worker that
# was hard-killed (OOM/SIGKILL) mid-run, so its own refund-on-failure never ran.
# Tunable via STUCK_JOB_MINUTES (default 30) — keep it safely beyond the longest
# legitimate run (video tops out at ~20 min).
STUCK_AFTER_SECONDS = settings.stuck_job_minutes * 60


async def _expire_subscriptions(ctx) -> None:
    # This runs hourly. Auto-renewal (daily 03:00) documents a grace window in which
    # a just-lapsed sub can still be renewed — but its selection requires sub_tier to
    # still be set. If we cleared every lapsed sub here, an auto-renew user would have
    # their tier nulled within the hour and be excluded from the next renewal sweep,
    # silently killing the grace backstop. So keep auto-renew users inside the grace
    # window; clear everyone else (and grace-exhausted auto-renewers) immediately.
    from core.services.autorenew import RENEWAL_GRACE_HOURS

    now = datetime.now(UTC)
    grace_cutoff = now - timedelta(hours=RENEWAL_GRACE_HOURS)
    async with SessionFactory() as session:
        await session.execute(
            update(User)
            .where(
                User.sub_expires < now,
                or_(User.auto_renew.is_(False), User.sub_expires < grace_cutoff),
            )
            .values(sub_tier=None, sub_expires=None)
        )
        await session.commit()


async def _sweep_stuck_jobs(ctx) -> None:
    """Refund + fail generation jobs stuck in pending/processing past the ceiling.

    Backstop for a hard worker crash: the normal per-worker refund-on-failure
    can't run if the process was killed, leaving the charge consumed and the job
    frozen. Each job is claimed with a conditional UPDATE — only the transaction
    whose UPDATE still matches a pending/processing status wins, so a worker
    finishing at the same instant (or a concurrent sweep) can never double-refund.
    The video/music workers also re-check ``status == 'processing'`` before their
    terminal transitions, so a swept job they later touch is a no-op.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=STUCK_AFTER_SECONDS)
    async with SessionFactory() as session:
        ids = (await session.scalars(
            select(GenerationJob.job_id)
            .where(
                GenerationJob.status.in_(("pending", "processing")),
                GenerationJob.created_at < cutoff,
            )
            .limit(200)
        )).all()

    for job_id in ids:
        async with SessionFactory() as session:
            claimed = await session.execute(
                update(GenerationJob)
                .where(
                    GenerationJob.job_id == job_id,
                    GenerationJob.status.in_(("pending", "processing")),
                )
                .values(
                    status="failed",
                    error="stuck: worker did not finish (swept)",
                    completed_at=datetime.now(UTC),
                )
            )
            if claimed.rowcount == 0:
                continue  # the worker resolved it between our SELECT and UPDATE
            job = await session.get(GenerationJob, job_id)
            if job is not None:
                await refund_job(session, job)  # canonical 🪙/pack/free-slot reversal
            await session.commit()


# cron schedules (UTC): hourly expiry sweep; stuck-job sweep every 5 min (matches
# the avatar sweep cadence in workers.main).
#
# NOTE: there is intentionally NO mass weekly quota-reset cron. The weekly text
# allowance resets lazily per user inside core.services.quota._maybe_reset_weekly
# (on the user's next request), so an inactive user's stale counter is harmless
# and we avoid a full-table `UPDATE users` that, at millions of rows, would rewrite
# every row weekly (WAL spike, bloat, autovacuum pressure, lock contention). The
# lazy reset is the single source of truth — see core/services/quota.py.
expire_subscriptions = cron(_expire_subscriptions, minute=0)
sweep_stuck_jobs = cron(
    _sweep_stuck_jobs, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}
)
