"""Safety-net «генерация готова» notifier (ТЗ §3).

A backstop for the per-worker delivery path: if a worker finished an async
generation job but — for any reason (crash after the status write, a delivery
exception, a blocked send that wasn't retried) — never told the user, this cron
pings them once. Dedupe is Redis-only (key ``gen_notified:{job_id}``, ~6h TTL),
so there is no new column / migration and a re-tick can't double-send.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionFactory
from core.models import GenerationJob, User
from core.redis_client import first_seen

# 6h is comfortably longer than the cron interval (5 min) and the notify window
# (30 min), so a job is announced at most once even across a beat restart.
_DEDUPE_TTL = 6 * 3600


async def recently_completed_unnotified(
    session: AsyncSession, since_minutes: int = 30
) -> list[GenerationJob]:
    """Jobs that reached ``completed`` within the last ``since_minutes``.

    Uses ``completed_at`` when set (the worker's terminal write) and falls back
    to ``created_at`` for any legacy row that lacks it. The "already notified"
    filter is applied in the runner via the Redis dedupe key, not here, so this
    query stays a plain time-window scan over the (status, created_at) index.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=max(0, since_minutes))
    completed = func.coalesce(GenerationJob.completed_at, GenerationJob.created_at)
    rows = await session.scalars(
        select(GenerationJob)
        # The workers write the success status as "complete" (not "completed");
        # the wrong spelling here matched nothing, so this safety-net never fired.
        .where(GenerationJob.status == "complete", completed >= cutoff)
        .limit(200)
    )
    return list(rows)


async def _locales_for(session: AsyncSession, user_ids: set[int]) -> dict[int, str]:
    """Map each user_id to its language (default 'ru') in ONE query, so the runner
    doesn't pay a per-job ``session.get(User)`` round-trip (a tick can carry up to
    200 jobs)."""
    if not user_ids:
        return {}
    rows = await session.execute(
        select(User.user_id, User.language_code).where(User.user_id.in_(user_ids))
    )
    return {uid: (lang or "ru") for uid, lang in rows}


async def run_gen_notify(session: AsyncSession | None = None) -> int:
    """Ping each user whose recent generation completed but wasn't yet announced.

    Per-job best-effort: a failed send (blocked/deactivated user) is skipped and
    never aborts the run. ``first_seen`` atomically claims the per-job dedupe key
    (``gen_notified:{job_id}``, ~6h TTL) so overlapping ticks can't double-announce.
    Returns the count of users notified."""
    if session is None:
        async with SessionFactory() as own:
            return await run_gen_notify(own)

    from core.bot_client import get_bot
    from core.i18n import t

    bot = get_bot()
    notified = 0
    # Claim each job's dedupe key first, then fetch locales for ONLY the survivors in
    # one query — a steady-state tick mostly re-sees jobs it already announced, so
    # fetching locales up-front for the whole window would mostly be wasted rows.
    jobs = await recently_completed_unnotified(session)
    survivors = [j for j in jobs if await first_seen(f"gen_notified:{j.job_id}", _DEDUPE_TTL)]
    locales = await _locales_for(session, {j.user_id for j in survivors})
    for job in survivors:
        try:
            await bot.send_message(
                job.user_id,
                t("gen.ready_generic", locales.get(job.user_id, "ru"), service=job.service),
            )
        except Exception:  # noqa: BLE001 — blocked/deactivated users etc.
            continue
        notified += 1
    return notified
