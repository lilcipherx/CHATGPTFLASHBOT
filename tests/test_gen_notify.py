"""«Генерация готова» safety-net notifier (ТЗ §3).

GenerationJobs are seeded in a real SQLite DB (create_all fixture, same as
test_notify). The Bot is monkeypatched to a fake recorder so no network is
touched, and Redis (fakeredis) is flushed between sub-tests so the dedupe window
doesn't leak.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, GenerationJob
from core.redis_client import redis_client
from core.services import gen_notify, pricing


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await redis_client.flushall()
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield
    try:
        await pricing.redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


class _FakeBot:
    """Records (user_id, text) instead of hitting Telegram."""

    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, user_id, text, **kwargs):
        self.sent.append((user_id, text))


@pytest.fixture
def fake_bot(monkeypatch):
    bot = _FakeBot()
    monkeypatch.setattr("core.bot_client.get_bot", lambda: bot)
    return bot


async def _add(session, **kw):
    job = GenerationJob(**kw)
    session.add(job)
    return job


async def _seed():
    now = datetime.now(UTC)
    async with SessionFactory() as s:
        # should notify: completed inside the 30-min window (real worker status)
        fresh = await _add(
            s, user_id=10, service="image", status="complete",
            completed_at=now - timedelta(minutes=2),
        )
        # no notify: completed long ago (outside the window)
        await _add(
            s, user_id=20, service="video", status="complete",
            completed_at=now - timedelta(hours=3),
        )
        # no notify: still pending
        await _add(
            s, user_id=30, service="music", status="pending",
            created_at=now - timedelta(minutes=1),
        )
        await s.commit()
        return fresh.job_id


async def test_notifies_only_recent_completed(fake_bot):
    await _seed()
    n = await gen_notify.run_gen_notify()
    assert n == 1
    assert len(fake_bot.sent) == 1
    user_id, text = fake_bot.sent[0]
    assert user_id == 10
    assert text == "✅ Ваша генерация (image) готова."


async def test_dedupe_no_resend_in_window(fake_bot):
    await _seed()
    first = await gen_notify.run_gen_notify()
    assert first == 1
    # a second run in the same window must not re-notify (Redis dedupe)
    second = await gen_notify.run_gen_notify()
    assert second == 0
    assert len(fake_bot.sent) == 1
