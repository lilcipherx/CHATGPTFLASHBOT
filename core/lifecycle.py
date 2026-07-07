"""Shared async task-lifecycle helpers."""
from __future__ import annotations

import asyncio
from contextlib import suppress


async def cancel_and_drain(*tasks: asyncio.Task | None) -> None:
    """Cancel each task then await it so cancellation actually settles before the
    caller tears the rest down — no "Task was destroyed but it is pending" warning,
    and no half-open resource (DB session, aiohttp client) a cancelled coroutine was
    parked on. ``None`` entries are skipped, so a loop that was never started is fine.

    Used identically by the API lifespan, the ARQ worker on_shutdown, and the bot
    polling loop, so the cancellation policy lives in one place.
    """
    live = [t for t in tasks if t is not None]
    for t in live:
        t.cancel()
    for t in live:
        with suppress(asyncio.CancelledError):
            await t
