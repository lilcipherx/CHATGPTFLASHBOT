"""Integration: the ARQ worker startup must START the provider-key refresh loop,
not just load keys once — mirroring the API lifespan (test_api_lifespan_refresh).

A long-running worker process applies provider keys at boot via load_once(). If it
never refreshes, a provider key added/rotated in the admin panel after startup never
reaches the worker, so media generation keeps failing (and refunding) until someone
restarts the worker. The bot and API both run provider_keys.refresh_loop(); this
guards that the worker does too, and that shutdown cancels it (no task leak).

i18n overrides are intentionally NOT loaded in the worker — no worker code path
renders override-backed text — so only the provider-key loop is asserted here.
"""
from __future__ import annotations

import asyncio

import pytest

from core.services import provider_keys
from workers import main as wmain


@pytest.mark.asyncio
async def test_worker_startup_starts_and_stops_key_refresh(monkeypatch):
    loaded = asyncio.Event()
    started = asyncio.Event()

    async def _fake_load_once():
        loaded.set()

    async def _fake_refresh_loop(interval: int = 30):
        started.set()
        try:
            await asyncio.sleep(3600)  # park like the real loop until cancelled
        except asyncio.CancelledError:
            raise

    # close_bot is called on shutdown; stub it so the test needs no real Bot.
    async def _fake_close_bot():
        return None

    monkeypatch.setattr(provider_keys, "load_once", _fake_load_once)
    monkeypatch.setattr(provider_keys, "refresh_loop", _fake_refresh_loop)
    monkeypatch.setattr("core.bot_client.close_bot", _fake_close_bot)

    ctx: dict = {}
    await wmain._on_startup(ctx)

    # load_once ran AND a live refresh task was scheduled.
    assert loaded.is_set()
    task = ctx.get("_key_refresh")
    assert task is not None and not task.done()
    await asyncio.wait_for(started.wait(), timeout=2)

    # Shutdown must cancel the loop — no leaked background task.
    await wmain._on_shutdown(ctx)
    await asyncio.sleep(0)  # let the cancellation propagate
    assert task.cancelled() or task.done()
