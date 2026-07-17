"""A-1 perf fix (load-test finding): `/api/profile` is the hottest Mini App
endpoint and its `_miniapp_sections()` fan-out re-queries provider availability
(`ai_routing.candidate_accounts`, one DB round-trip per modality) on EVERY call,
even though provider availability + the admin section override change rarely.

This asserts the sections result is cached across calls so a burst of profile
loads does not re-hit the DB for section availability every time. Provider
availability changing is bounded by the cache TTL.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

import core.services.ai_routing as ai_routing
from api.routers.miniapp import _miniapp_sections
from core.db import SessionFactory, engine
from core.models import Base
from core.redis_client import redis_client

# Stable cache-key contract (kept in sync with api.routers.miniapp).
_SECTIONS_CACHE_KEY = "cache:miniapp_sections"
_CONFIG_CACHE_KEY = "cache:business_config"


@pytest_asyncio.fixture(autouse=True)
async def _tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.mark.asyncio
async def test_miniapp_sections_cached_across_calls(monkeypatch):
    # Clear any cache leaked from other tests so get_config recomputes from the
    # (override-free) DB → sections mode is "auto" → candidate_accounts IS consulted.
    for key in (_SECTIONS_CACHE_KEY, _CONFIG_CACHE_KEY):
        try:
            await redis_client.delete(key)
        except Exception:
            pass

    calls = {"n": 0}

    async def _counting(session, modality="text", *, kind=None):
        calls["n"] += 1
        return []

    monkeypatch.setattr(ai_routing, "candidate_accounts", _counting)

    async with SessionFactory() as s:
        first = await _miniapp_sections(s)
        after_first = calls["n"]
        second = await _miniapp_sections(s)
        after_second = calls["n"]

    # Same answer both times.
    assert first == second
    # First call actually computed availability (hit the provider DB check).
    assert after_first >= 1
    # Second call must be served from cache — zero extra provider DB queries.
    assert after_second == after_first, (
        f"_miniapp_sections re-queried providers on a cache-warm call: "
        f"{after_first} -> {after_second}"
    )
