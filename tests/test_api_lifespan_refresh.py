"""Integration: the API lifespan must start the provider-key + localization refresh
loops, not just load them once.

Production serves the API (and, in webhook mode, the Telegram bot updates) from a
gunicorn pool of N worker processes. An admin write (provider_keys.set_keys /
i18n_overrides.set_override) mutates only the one worker that served the request; the
others converge solely via the periodic refresh_loop. If the lifespan only called
load_once(), a freshly-entered AI key would work for just ~1/N of requests and
localization edits would render inconsistently across workers until a restart.

This guards that both loops are scheduled on startup and cancelled on shutdown.
"""
from __future__ import annotations

import asyncio

import pytest

from api.main import app, lifespan
from core.services import i18n_overrides, provider_keys


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_both_refresh_loops(monkeypatch):
    started: set[str] = set()
    ran = asyncio.Event()

    def _make(name: str):
        async def _loop(interval: int = 30):
            started.add(name)
            if len(started) == 2:
                ran.set()
            try:
                await asyncio.sleep(3600)  # park like the real loop, until cancelled
            except asyncio.CancelledError:
                raise

        return _loop

    # Don't touch the DB in load_once during the test; we only assert loop wiring.
    async def _noop():
        return None

    monkeypatch.setattr(provider_keys, "load_once", _noop)
    monkeypatch.setattr(i18n_overrides, "load_once", _noop)
    monkeypatch.setattr(provider_keys, "refresh_loop", _make("provider_keys"))
    monkeypatch.setattr(i18n_overrides, "refresh_loop", _make("i18n_overrides"))

    async with lifespan(app):
        # Both loops must have been scheduled by the time the app is serving traffic.
        await asyncio.wait_for(ran.wait(), timeout=2)
        assert started == {"provider_keys", "i18n_overrides"}
        # Capture the live loop tasks so we can prove shutdown cancels them.
        loop_tasks = [
            t for t in asyncio.all_tasks()
            if t.get_coro().__qualname__.endswith("_make.<locals>._loop")
        ]
        assert len(loop_tasks) == 2

    # After the lifespan exits, the refresh tasks must be cancelled (no leak).
    await asyncio.sleep(0)  # let the cancellations propagate
    assert all(t.cancelled() or t.done() for t in loop_tasks)
