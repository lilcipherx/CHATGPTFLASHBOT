"""Cron task: daily Premium auto-renewal sweep (ТЗ §6).

Selects opted-in premium users whose subscription is about to lapse and charges
each off-session against the payment method they vaulted at checkout, extending the
subscription on success — see core.services.autorenew for details.
"""
from __future__ import annotations

from arq import cron

from core.db import SessionFactory
from core.services.autorenew import run_autorenew


async def process_autorenewals(ctx) -> dict[str, int]:
    """ARQ entrypoint: open a session and run the auto-renewal sweep."""
    async with SessionFactory() as session:
        return await run_autorenew(session)


# Daily at 03:00 UTC — runs once per day in the off-peak window, mirroring the
# other daily housekeeping crons. Lives in BeatSettings (single scheduler).
renew_subscriptions = cron(process_autorenewals, hour=3, minute=0)
