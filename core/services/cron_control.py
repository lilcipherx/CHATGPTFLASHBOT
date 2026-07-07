"""Admin-controlled scheduling gate for the beat cron jobs.

The beat scheduler (workers.main) ticks every job once a minute; before running, the
job calls :func:`claim` which reads its ``cron_jobs`` row and answers "run now?" —
True only when the job is ENABLED and its configured ``interval_seconds`` has elapsed
since ``last_run_at``. The admin panel edits those rows (enable/disable + interval),
so scheduling is controlled at runtime with no redeploy.

``JOBS`` is the single source of truth for which jobs exist and their DEFAULT interval
(reasonable defaults chosen by the maintainer; all tunable in the panel). A job missing
from a DB is auto-created on first tick / first admin list with its default.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.cron import CronJob

# name -> (human label for the admin panel, default interval in seconds).
JOBS: dict[str, tuple[str, int]] = {
    "expire_subscriptions": ("Истечение подписок", 3600),
    "sweep_stuck_jobs": ("Возврат зависших генераций", 300),
    "claim_pending_avatars": ("Досбор зависших аватаров", 300),
    "dispatch_scheduled_broadcasts": ("Отправка запланированных рассылок", 60),
    "sweep_stuck_broadcasts": ("Досбор зависших рассылок", 300),
    "send_notifications": ("Ежедневные уведомления пользователям", 86400),
    "publish_channel_posts": ("Публикация постов в каналы", 60),
    "sweep_stuck_channel_posts": ("Досбор зависших постов канала", 300),
    "prune_results": ("Очистка старых результатов генераций", 86400),
    "purge_old_audit_logs": ("Очистка старых аудит-логов", 86400),
    "purge_old_transactions": ("Очистка старых транзакций", 86400),
    "purge_old_support_messages": ("Очистка старых сообщений поддержки", 86400),
    "renew_subscriptions": ("Авто-продление Premium", 86400),
    "gen_ready_notifications": ("Уведомления «генерация готова»", 300),
    "send_scheduled_report": ("Ежедневный админ-отчёт", 86400),
}

MIN_INTERVAL = 30            # never let a job hammer every tick
MAX_INTERVAL = 7 * 86400     # a week between runs is the practical ceiling


async def _get_or_create(session: AsyncSession, name: str) -> CronJob | None:
    row = await session.get(CronJob, name)
    if row is not None:
        return row
    _label, interval = JOBS.get(name, (name, 3600))
    row = CronJob(name=name, enabled=True, interval_seconds=interval)
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        # Concurrent create (another tick) — reuse the existing row.
        await session.rollback()
        row = await session.get(CronJob, name)
    return row


async def claim(session: AsyncSession, name: str) -> bool:
    """Return True (and stamp ``last_run_at``) if ``name`` should run now: enabled and
    its interval has elapsed. Called from the beat tick, once per minute per job. The
    beat runs as a single replica, so no cross-process race; a lost DB read just skips
    this tick and the job runs on the next one."""
    row = await _get_or_create(session, name)
    if row is None or not row.enabled:
        return False
    now = datetime.now(UTC)
    last = row.last_run_at
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if (now - last).total_seconds() < row.interval_seconds:
            return False
    row.last_run_at = now
    await session.commit()
    return True


async def record_result(session: AsyncSession, name: str, status: str) -> None:
    """Best-effort: store a short outcome of the last run for the admin panel."""
    row = await session.get(CronJob, name)
    if row is None:
        return
    row.last_status = (status or "")[:200]
    await session.commit()


async def list_jobs(session: AsyncSession) -> list[dict]:
    """All known jobs (auto-creating any missing rows) for the admin panel."""
    out: list[dict] = []
    for name, (label, _iv) in JOBS.items():
        row = await _get_or_create(session, name)
        if row is None:
            continue
        out.append({
            "name": name,
            "label": label,
            "enabled": row.enabled,
            "interval_seconds": row.interval_seconds,
            "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
            "last_status": row.last_status,
        })
    await session.commit()
    return out


async def set_config(
    session: AsyncSession,
    name: str,
    *,
    enabled: bool | None = None,
    interval_seconds: int | None = None,
) -> dict:
    """Update a job's enabled flag / interval (admin panel). Raises KeyError for an
    unknown job name and clamps the interval to [MIN_INTERVAL, MAX_INTERVAL]."""
    if name not in JOBS:
        raise KeyError(name)
    row = await _get_or_create(session, name)
    if row is None:
        raise KeyError(name)
    if enabled is not None:
        row.enabled = enabled
    if interval_seconds is not None:
        row.interval_seconds = max(MIN_INTERVAL, min(MAX_INTERVAL, int(interval_seconds)))
    await session.commit()
    label = JOBS[name][0]
    return {
        "name": name,
        "label": label,
        "enabled": row.enabled,
        "interval_seconds": row.interval_seconds,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_status": row.last_status,
    }
