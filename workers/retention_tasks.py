"""Cron task: prune generation/gallery artifacts past the admin retention window (§5)."""
from __future__ import annotations

from arq import cron

from core.db import SessionFactory
from core.services.retention import run_retention


async def prune_old_results(ctx) -> dict[str, int]:
    """Daily retention sweep: delete artifacts older than the configured windows."""
    async with SessionFactory() as session:
        return await run_retention(session)


# Daily at 04:00 UTC — a quiet hour, well clear of the 09:00 notification cron.
prune_results = cron(prune_old_results, hour=4, minute=0)
