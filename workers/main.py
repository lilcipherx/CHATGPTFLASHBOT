"""ARQ workers, split into two roles so cron runs exactly once:

* ``WorkerSettings`` — processes queued generation jobs. SAFE TO SCALE to N
  replicas; it has NO cron_jobs, so scaling never multiplies scheduled tasks.
      Run: arq workers.main.WorkerSettings

* ``BeatSettings`` — the single scheduler. Holds the cron_jobs (subscription
  expiry, stuck-job sweep, pending-avatar sweep) and enqueues work for the
  worker pool. Run EXACTLY ONE replica. (Weekly text-quota reset is lazy per
  user — see workers.billing_tasks — so there is no mass-UPDATE cron here.)
      Run: arq workers.main.BeatSettings
"""
from __future__ import annotations

from arq import cron
from arq.connections import RedisSettings

from core.config import settings
from core.queue import CRON_QUEUE_NAME, WORKER_QUEUE_NAME
from workers.autorenew_tasks import renew_subscriptions
from workers.avatar_tasks import claim_pending_avatars, process_avatar_job
from workers.billing_tasks import (
    expire_subscriptions,
    sweep_stuck_jobs,
)
from workers.broadcast_tasks import (
    dispatch_scheduled_broadcasts,
    run_broadcast,
    sweep_stuck_broadcasts,  # FIX: AUDIT12-40
)
from workers.channel_tasks import (
    publish_channel_posts,
    sweep_stuck_channel_posts,  # FIX: AUDIT12-41
)
from workers.gen_notify_tasks import gen_ready_notifications
from workers.music_tasks import process_music_job
from workers.notify_tasks import send_notifications
from workers.photo_tools_tasks import process_faceswap_job, process_upscale_job
from workers.photoeffect_tasks import process_photoeffect_job
from workers.report_tasks import send_scheduled_report

# FIX: AUDIT12-M5 - additional retention sweeps for compliance tables.
from workers.retention_extra_tasks import (
    purge_old_audit_logs,
    purge_old_support_messages,
    purge_old_transactions,
)
from workers.retention_tasks import prune_results
from workers.video_tasks import process_video_job


def _redis_settings() -> RedisSettings:
    """ARQ needs a redis:// / rediss:// DSN. In zero-infra dev mode REDIS_URL is
    `memory://` (fakeredis) — arq can't parse that, so fall back to localhost
    defaults so the worker module still imports (it won't run without a real
    Redis, but importing it for introspection/tests must not crash)."""
    if settings.redis_url.startswith(("redis://", "rediss://", "unix://")):
        return RedisSettings.from_dsn(settings.redis_url)
    return RedisSettings()


# FIX: AUDIT12-43 - init Sentry in workers/beat so provider errors get reported.
# Was: only api/main.py and bot/main.py initialized Sentry → worker crashes
# (which is where most provider timeouts/auth-errors surface) were silently lost.
if settings.sentry_dsn:
    import sentry_sdk
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env, traces_sample_rate=0.1)


async def ping(ctx) -> str:
    return "pong"


# --- Admin-controlled scheduling -------------------------------------------------
# FIX: AUDIT-SCHED - the beat scheduler is now DB-driven so it can be controlled from
# the admin panel. Each job is ticked once a minute (below); core.services.cron_control
# decides — per its `cron_jobs` row — whether it's ENABLED and whether its configured
# interval has elapsed. This also fixes the previous crash where main.py wrapped names
# that were ALREADY arq CronJob objects in their modules (`cron(cron(...))` → arq
# "not a coroutine function"): `_managed` unwraps a CronJob via `.coroutine`, so a raw
# coroutine and a pre-wrapped CronJob are both accepted.
_EVERY_MINUTE = set(range(60))


def _managed(name: str, fn):
    """Wrap a cron coroutine with the admin on/off + interval gate. ``fn`` may be a raw
    coroutine function OR an arq ``CronJob`` (some task modules pre-wrap theirs); either
    way we run the underlying coroutine, and only when cron_control.claim() allows it."""
    coro = getattr(fn, "coroutine", fn)

    async def _run(ctx):
        from core.db import SessionFactory
        from core.services import cron_control
        async with SessionFactory() as session:
            if not await cron_control.claim(session, name):
                return None
        try:
            result = await coro(ctx)
            status = "ok"
        except Exception as exc:  # noqa: BLE001 - record + re-raise so arq logs/retries
            status = f"error: {exc}"
            raise
        finally:
            try:
                from core.db import SessionFactory as _SF
                from core.services import cron_control as _cc
                async with _SF() as s2:
                    await _cc.record_result(s2, name, status)
            except Exception:  # noqa: BLE001 - result bookkeeping must never mask the job
                pass
        return result

    _run.__name__ = f"cron_{name}"
    _run.__qualname__ = _run.__name__
    return _run


def _tick(name: str, fn, timeout: int):
    """A cron entry that fires every minute; the real cadence lives in the DB row."""
    return cron(_managed(name, fn), minute=_EVERY_MINUTE, second={0}, timeout=timeout)


async def _on_startup(ctx) -> None:
    """Apply admin-managed provider API keys onto settings so media generation in
    this worker uses keys entered in the admin panel (not just .env), then keep them
    fresh with a background refresh loop — exactly like the bot and API processes.

    load_once() alone pins the keys at boot: a provider key added/rotated in the
    admin panel after startup would never reach a long-running worker, so media
    generation would keep failing (and refunding) until the worker was restarted.
    The refresh loop re-applies DB keys every ~30s so the change propagates without a
    restart. (i18n overrides are deliberately NOT loaded here — no worker code path
    renders override-backed text; worker user messages are inline copy.)"""
    import asyncio

    from core.services import provider_keys

    await provider_keys.load_once()
    ctx["_key_refresh"] = asyncio.create_task(provider_keys.refresh_loop())


async def _on_shutdown(ctx) -> None:
    """Cancel the key-refresh loop and close the process-wide shared Bot (delivery /
    refund notifications use it via core.bot_client.get_bot) so its aiohttp session
    is released cleanly on stop."""
    from core.bot_client import close_bot
    from core.lifecycle import cancel_and_drain

    await cancel_and_drain(ctx.get("_key_refresh"))
    await close_bot()


class WorkerSettings:
    """Job-processing pool. NO cron_jobs here — scheduled tasks live in
    BeatSettings so running multiple worker replicas can't fire each cron N times.

    Consumes WORKER_QUEUE_NAME only. Beat's cron records live on CRON_QUEUE_NAME, so this
    pool never dequeues an unresolvable ``cron:*`` job (which it would log as
    "function not found" and discard — see the queue-isolation fix)."""

    redis_settings = _redis_settings()
    queue_name = WORKER_QUEUE_NAME
    on_startup = _on_startup
    on_shutdown = _on_shutdown
    functions = [
        ping,
        process_avatar_job,
        process_video_job,
        process_music_job,
        process_photoeffect_job,
        process_faceswap_job,
        process_upscale_job,
        run_broadcast,
    ]


class BeatSettings:
    """Single scheduler replica — owns every cron job. Run EXACTLY ONE instance
    (its tasks enqueue work that the WorkerSettings pool then processes).

    Isolated onto CRON_QUEUE_NAME: arq's ``run_cron`` enqueues each cron record to this
    worker's own ``queue_name`` (arq 0.26.3, Worker.run_cron), so keeping beat on a
    dedicated queue stops the pool from ever seeing ``cron:*`` jobs. Work that beat
    schedules for the pool is enqueued to WORKER_QUEUE_NAME explicitly (core.queue.enqueue
    pins that; the one ctx-pool dispatch in avatar_tasks passes _queue_name)."""

    redis_settings = _redis_settings()
    queue_name = CRON_QUEUE_NAME
    on_startup = _on_startup
    on_shutdown = _on_shutdown
    functions = [ping]  # arq needs a function list; cron callables live below
    # Every job ticks once a minute; core.services.cron_control (its `cron_jobs` DB
    # row, editable in the admin panel) decides if it's enabled and whether enough
    # time has passed since its last run. The `timeout` here still bounds a single run.
    cron_jobs = [
        _tick("expire_subscriptions", expire_subscriptions, 300),
        _tick("sweep_stuck_jobs", sweep_stuck_jobs, 300),
        _tick("claim_pending_avatars", claim_pending_avatars, 300),
        _tick("dispatch_scheduled_broadcasts", dispatch_scheduled_broadcasts, 120),
        _tick("sweep_stuck_broadcasts", sweep_stuck_broadcasts, 300),
        _tick("send_notifications", send_notifications, 600),
        _tick("publish_channel_posts", publish_channel_posts, 120),
        _tick("sweep_stuck_channel_posts", sweep_stuck_channel_posts, 300),
        _tick("prune_results", prune_results, 1800),
        _tick("purge_old_audit_logs", purge_old_audit_logs, 1800),
        _tick("purge_old_transactions", purge_old_transactions, 1800),
        _tick("purge_old_support_messages", purge_old_support_messages, 1800),
        _tick("renew_subscriptions", renew_subscriptions, 1800),
        _tick("gen_ready_notifications", gen_ready_notifications, 300),
        _tick("send_scheduled_report", send_scheduled_report, 600),
    ]
