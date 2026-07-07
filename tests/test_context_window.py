"""Rolling chat-memory window (§3.2): append_context trims to max_pairs, in order."""
from __future__ import annotations

import pytest_asyncio

from core.services.context import append_context, clear_context, get_context


@pytest_asyncio.fixture(autouse=True)
async def _clean_redis():
    from core.redis_client import redis_client

    await clear_context(42)
    yield
    try:
        await redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


async def test_keeps_only_last_n_in_order():
    n = 5
    for i in range(n + 2):  # append N+2 pairs
        await append_context(42, f"q{i}", f"a{i}", max_pairs=n)
    pairs = await get_context(42)
    assert len(pairs) == n
    # Only the last N remain, chronological (oldest -> newest).
    assert [p["q"] for p in pairs] == [f"q{i}" for i in range(2, n + 2)]
    assert [p["a"] for p in pairs] == [f"a{i}" for i in range(2, n + 2)]


async def test_max_pairs_floor_is_one():
    for i in range(3):
        await append_context(42, f"q{i}", f"a{i}", max_pairs=0)
    pairs = await get_context(42)
    assert len(pairs) == 1 and pairs[0]["q"] == "q2"
