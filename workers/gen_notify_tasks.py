"""Cron task: «генерация готова» safety-net notifier (ТЗ §3).

Mirrors the billing_tasks cron shape — a ``ctx``-arg entrypoint wrapped in
``arq.cron`` — and opens its own SessionFactory session for the run. Lives on the
single BeatSettings scheduler so the pings fire exactly once per tick.
"""
from __future__ import annotations

from arq import cron

from core.db import SessionFactory
from core.services.gen_notify import run_gen_notify


async def notify_completed(ctx) -> int:
    """Open a session and ping users whose generation finished undelivered."""
    async with SessionFactory() as session:
        return await run_gen_notify(session)


# Every 5 min — matches the stuck-job sweep cadence. Redis dedupe (gen_notify.py)
# makes an extra tick harmless, so a tight cadence just shortens the worst-case
# wait before a stranded user is told their result is ready.
gen_ready_notifications = cron(notify_completed, minute=set(range(0, 60, 5)))
