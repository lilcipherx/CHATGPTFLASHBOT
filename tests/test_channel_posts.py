"""Channel autoposting (ТЗ §7) — service selectors/transitions + admin create.

Calls the endpoint coroutines directly (FastAPI leaves them callable) against a
real SQLite DB, mirroring tests/test_business_admin. No live bot is required —
the cron's send path is not exercised here; the service `due()`/transitions are."""
from __future__ import annotations

import types
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import func, select

from api.admin import channel
from core.db import SessionFactory, engine
from core.models import AdminAuditLog, AdminUser, Base
from core.models.channel_post import ChannelPost  # noqa: F401 — registers table
from core.services import channel_posts
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req():
    return types.SimpleNamespace(client=None)


async def _admin(session, role="admin") -> AdminUser:
    a = AdminUser(email="c@x.io", password_hash=hash_password("x"), role=role, is_active=True)
    session.add(a)
    await session.commit()
    return a


async def test_create_persists_pending():
    async with SessionFactory() as s:
        post = await channel_posts.create(s, channel="@chan", text="hi")
        assert post.id is not None
        assert post.status == "pending"
        assert post.channel == "@chan"


async def test_due_selects_past_and_unscheduled_not_future_or_sent():
    now = datetime.now(UTC)
    async with SessionFactory() as s:
        asap = await channel_posts.create(s, channel="@c", text="asap")  # no schedule
        past = await channel_posts.create(
            s, channel="@c", text="past", scheduled_at=now - timedelta(minutes=5)
        )
        future = await channel_posts.create(
            s, channel="@c", text="future", scheduled_at=now + timedelta(hours=1)
        )
        sent = await channel_posts.create(s, channel="@c", text="sent")
        await channel_posts.mark_sent(s, sent)

        due = await channel_posts.due(s, now)
        due_ids = {p.id for p in due}
        assert asap.id in due_ids
        assert past.id in due_ids
        assert future.id not in due_ids
        assert sent.id not in due_ids


async def test_mark_sent_and_failed_flip_status():
    async with SessionFactory() as s:
        p1 = await channel_posts.create(s, channel="@c", text="ok")
        await channel_posts.mark_sent(s, p1)
        assert p1.status == "sent"
        assert p1.sent_at is not None

        p2 = await channel_posts.create(s, channel="@c", text="bad")
        await channel_posts.mark_failed(s, p2, "boom")
        assert p2.status == "failed"
        assert p2.error == "boom"


class _FakeBot:
    """Records the kwargs of each send so the test can assert on parse_mode."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_message(self, **kw):
        self.calls.append({"kind": "message", **kw})

    async def send_photo(self, **kw):
        self.calls.append({"kind": "photo", **kw})


async def test_worker_publishes_with_html_parse_mode(monkeypatch):
    """Regression: the autoposting worker MUST send with parse_mode='HTML' so the
    formatting toolbar (<b>/<i>/<a>…) renders in the channel instead of leaking raw
    tags. Covers both the text and the photo-caption paths."""
    import core.bot_client
    from workers.channel_tasks import dispatch_channel_posts

    bot = _FakeBot()
    monkeypatch.setattr(core.bot_client, "get_bot", lambda: bot)

    async with SessionFactory() as s:
        await channel_posts.create(s, channel="@c", text="<b>hi</b>")
        await channel_posts.create(s, channel="@c", text="cap", photo_url="https://x/p.jpg")

    await dispatch_channel_posts(ctx=None)

    assert len(bot.calls) == 2
    assert all(c["parse_mode"] == "HTML" for c in bot.calls)
    kinds = {c["kind"] for c in bot.calls}
    assert kinds == {"message", "photo"}

    async with SessionFactory() as s:
        sent = await s.scalar(
            select(func.count()).select_from(ChannelPost).where(ChannelPost.status == "sent")
        )
        assert sent == 2  # both flipped to sent after a successful send


async def test_admin_create_writes_row_and_audits():
    async with SessionFactory() as s:
        a = await _admin(s, "admin")
        out = await channel.create_post(
            channel.ChannelPostRequest(channel="@news", text="hello"),
            _req(), admin=a, session=s,
        )
        assert out["channel"] == "@news"
        assert out["status"] == "pending"

    async with SessionFactory() as s:
        n_posts = await s.scalar(select(func.count()).select_from(ChannelPost))
        assert n_posts == 1
        n_audit = await s.scalar(
            select(func.count()).select_from(AdminAuditLog)
            .where(AdminAuditLog.action == "channel_post.create")
        )
        assert n_audit == 1
