"""Support inbox + admin DMs (api/admin/messaging + core/services/support) — ТЗ §7.

Calls the service helpers and admin endpoint coroutines directly against a real
SQLite DB, mirroring tests/test_business_admin. Telegram delivery is faked via a
monkeypatched ``get_bot`` that records send_message calls.
"""
from __future__ import annotations

import types

import pytest_asyncio
from sqlalchemy import func, select

from api.admin import messaging
from core.db import SessionFactory, engine
from core.models import AdminUser, Base
from core.models.support import SupportMessage
from core.services import support
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req():
    return types.SimpleNamespace(client=None)


async def _admin(session, role="support") -> AdminUser:
    a = AdminUser(email="s@x.io", password_hash=hash_password("x"), role=role, is_active=True)
    session.add(a)
    await session.commit()
    return a


class _FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


async def test_record_inbound_shows_in_open():
    async with SessionFactory() as s:
        await support.record_inbound(s, user_id=111, text="help me")
        open_msgs = await support.list_open(s)
        assert len(open_msgs) == 1
        assert open_msgs[0].user_id == 111
        assert open_msgs[0].text == "help me"


async def test_mark_handled_removes_from_open():
    async with SessionFactory() as s:
        msg = await support.record_inbound(s, user_id=222, text="question")
        await support.mark_handled(s, msg.id)
        assert await support.list_open(s) == []


async def test_message_user_sends_and_records_outbound(monkeypatch):
    fake = _FakeBot()
    monkeypatch.setattr(messaging, "get_bot", lambda: fake)
    async with SessionFactory() as s:
        a = await _admin(s)
        out = await messaging.message_user(
            user_id=333, body=messaging.MessageBody(text="hi there"),
            request=_req(), admin=a, session=s,
        )
        assert out == {"ok": True}
        assert fake.sent == [(333, "hi there")]
        n = await s.scalar(
            select(func.count()).select_from(SupportMessage)
            .where(SupportMessage.direction == "out", SupportMessage.user_id == 333)
        )
        assert n == 1


async def test_reply_marks_inbound_handled(monkeypatch):
    fake = _FakeBot()
    monkeypatch.setattr(messaging, "get_bot", lambda: fake)
    async with SessionFactory() as s:
        a = await _admin(s)
        inbound = await support.record_inbound(s, user_id=444, text="stuck")
        out = await messaging.support_reply(
            message_id=inbound.id, body=messaging.MessageBody(text="here's help"),
            request=_req(), admin=a, session=s,
        )
        assert out == {"ok": True}
        assert fake.sent == [(444, "here's help")]
        # Original inbound is now handled -> no longer in the open inbox.
        assert await support.list_open(s) == []
        refreshed = await s.get(SupportMessage, inbound.id)
        assert refreshed.handled is True


async def test_message_user_send_failure_returns_error(monkeypatch):
    class _BoomBot:
        async def send_message(self, chat_id, text):
            raise RuntimeError("blocked")

    monkeypatch.setattr(messaging, "get_bot", lambda: _BoomBot())
    async with SessionFactory() as s:
        a = await _admin(s)
        out = await messaging.message_user(
            user_id=555, body=messaging.MessageBody(text="x"),
            request=_req(), admin=a, session=s,
        )
        assert out["ok"] is False
        assert "blocked" in out["error"]
        # Nothing recorded on failure.
        n = await s.scalar(select(func.count()).select_from(SupportMessage))
        assert n == 0
