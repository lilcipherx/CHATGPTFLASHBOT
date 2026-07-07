"""Cron task: auto-engagement notifications (ТЗ §7).

Mirrors the billing_tasks cron shape — a ``ctx``-arg entrypoint wrapped in
``arq.cron`` — and opens its own SessionFactory session for the run. Runs on the
single BeatSettings scheduler so the nudges fire exactly once per tick.
"""
from __future__ import annotations

from arq import cron

from core.db import SessionFactory
from core.services.notify import run_notifications


async def _send_notifications(ctx) -> dict[str, int]:
    """Open a session and dispatch all enabled engagement nudges."""
    async with SessionFactory() as session:
        return await run_notifications(session)


# Once a day at 09:00 UTC — a friendly mid-morning window for most user timezones.
# Redis dedupe (notify.py) makes an extra tick harmless, but daily is the intent.
send_notifications = cron(_send_notifications, hour=9, minute=0)
