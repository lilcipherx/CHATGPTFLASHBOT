"""Integration: bot polling must START the provider-key + localization refresh loops
AND cancel them when polling ends — no leaked background task.

run_polling applies admin-managed keys/overrides at boot, then keeps them fresh with
two refresh loops while the dispatcher polls. Those loops must not outlive the
dispatcher: a bare create_task left running after start_polling returns (SIGTERM) is a
dangling task parked on a DB session. This mirrors test_api_lifespan_refresh and
test_worker_lifespan_refresh.
"""
from __future__ import annotations

import asyncio

import pytest

from bot import main as bmain
from core.services import i18n_overrides, provider_keys


@pytest.mark.asyncio
async def test_run_polling_starts_and_stops_both_refresh_loops(monkeypatch):
    started: set[str] = set()
    both_running = asyncio.Event()

    def _make(name: str):
        async def _loop(interval: int = 30):
            started.add(name)
            if len(started) == 2:
                both_running.set()
            await asyncio.sleep(3600)  # park like the real loop, until cancelled

        return _loop

    async def _noop():
        return None

    monkeypatch.setattr(provider_keys, "load_once", _noop)
    monkeypatch.setattr(i18n_overrides, "load_once", _noop)
    monkeypatch.setattr(provider_keys, "refresh_loop", _make("provider_keys"))
    monkeypatch.setattr(i18n_overrides, "refresh_loop", _make("i18n_overrides"))

    # Avoid touching Telegram / the DB: a dispatcher whose start_polling blocks until
    # we release it (standing in for "poll until SIGTERM"), and no real bots.
    release = asyncio.Event()

    class _FakeDp:
        async def start_polling(self, *bots):
            # Both loops should already be live by the time we're polling.
            await asyncio.wait_for(both_running.wait(), timeout=2)
            await release.wait()

    monkeypatch.setattr(bmain, "build_dispatcher", lambda: _FakeDp())
    monkeypatch.setattr(bmain, "_multi_bots", _noop)        # returns None → falls back
    monkeypatch.setattr(bmain, "build_bot", lambda: object())
    monkeypatch.setattr(bmain, "_prepare_bot", lambda bot: _noop())

    poll = asyncio.create_task(bmain.run_polling())
    await asyncio.wait_for(both_running.wait(), timeout=2)
    assert started == {"provider_keys", "i18n_overrides"}

    loop_tasks = [
        t for t in asyncio.all_tasks()
        if t.get_coro().__qualname__.endswith("_make.<locals>._loop")
    ]
    assert len(loop_tasks) == 2

    # End polling (SIGTERM) → run_polling's finally must cancel both loops.
    release.set()
    await asyncio.wait_for(poll, timeout=2)
    assert all(t.cancelled() or t.done() for t in loop_tasks)
