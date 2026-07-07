"""Premium queue priority (ТЗ §8): is_priority_job gating + ARQ score back-dating.

Premium users' generation jobs jump the ARQ queue when admin-enabled. The enqueue
back-dates ``_defer_until`` so the job sorts ahead; no real Redis/ARQ is needed —
the pool is stubbed."""
from __future__ import annotations

import types
from datetime import UTC, datetime, timedelta

import pytest_asyncio

from core import queue
from core.db import SessionFactory, engine
from core.models import Base, User
from core.services import pricing


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield


def _job(uid: int):
    return types.SimpleNamespace(user_id=uid, job_id="job-1")


async def _add(session, uid, *, premium: bool):
    u = User(user_id=uid, username=f"u{uid}")
    if premium:
        u.sub_tier = "premium"
        u.sub_expires = datetime.now(UTC) + timedelta(days=5)
    session.add(u)
    await session.commit()
    return u


async def test_priority_for_premium_user_default_on():
    async with SessionFactory() as s:
        await _add(s, 1, premium=True)
        assert await queue.is_priority_job(s, _job(1)) is True


async def test_no_priority_for_free_user():
    async with SessionFactory() as s:
        await _add(s, 2, premium=False)
        assert await queue.is_priority_job(s, _job(2)) is False


async def test_no_priority_when_admin_disables_it():
    async with SessionFactory() as s:
        await _add(s, 1, premium=True)
        await pricing.set_config(s, {"queue": {"premium_priority_enabled": False}})
        assert await queue.is_priority_job(s, _job(1)) is False


async def test_no_priority_for_missing_user():
    async with SessionFactory() as s:
        assert await queue.is_priority_job(s, _job(999)) is False


async def test_enqueue_backdates_defer_only_when_priority(monkeypatch):
    captured: list[tuple] = []

    class _FakePool:
        async def enqueue_job(self, function, *args, **kwargs):
            captured.append((function, args, kwargs))

    monkeypatch.setattr(queue, "_pool", _FakePool())

    await queue.enqueue("process_x", "a", priority=True)
    await queue.enqueue("process_x", "b", priority=False)

    # Priority job is back-dated far into the past so it sorts ahead of "now" jobs.
    assert "_defer_until" in captured[0][2]
    assert captured[0][2]["_defer_until"] < datetime.now(UTC) - timedelta(days=3000)
    # Normal job carries no defer override.
    assert "_defer_until" not in captured[1][2]
