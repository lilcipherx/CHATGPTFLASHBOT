"""Voice input (§30) admin controls: the `voice_input` master switch turns the
whole feature on/off, and `voice_input_free` decides the audience (Premium-only by
default, or open to free users). Both are surfaced in the admin panel /flags list."""
from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import pytest_asyncio

import bot.handlers.chat as chat
from core.db import SessionFactory, engine
from core.models import Base
from core.services import feature_flags
from core.services.feature_flags import default_flags
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


class _Bot:
    async def send_chat_action(self, *a, **k):
        return None

    async def download(self, *a, **k):
        return io.BytesIO(b"audio")


class _Msg:
    def __init__(self):
        self.bot = _Bot()
        self.chat = type("C", (), {"id": 1})()
        self.voice = type("V", (), {"file_id": "vf1"})()
        self.answers: list[str] = []

    async def answer(self, text, *a, **k):
        self.answers.append(text)
        return None


class _EmptySTT:
    """Transcribes to '' so on_voice stops at the `voice_in.empty` branch —
    proving both admin gates were passed WITHOUT running the full chat pipeline."""

    async def transcribe(self, data, locale=None):
        return ""


class _UnavailableSTT:
    async def transcribe(self, data, locale=None):
        from core.ai_router.base import ProviderUnavailable
        raise ProviderUnavailable("stt")


class _BrokenSTT:
    async def transcribe(self, data, locale=None):
        raise RuntimeError("boom")


def _tr(key, **kw):
    return key


async def _make_premium(s, uid):
    user, _ = await get_or_create_user(s, uid)
    user.sub_tier = "premium"
    user.sub_expires = datetime.now(UTC) + timedelta(days=30)
    await s.commit()
    return user


def test_new_flags_defaults():
    flags = default_flags()
    assert flags["voice_input"] is True          # master on by default
    assert flags["voice_input_free"] is False     # premium-only by default


async def test_master_switch_off_blocks_everyone(monkeypatch):
    monkeypatch.setattr("core.ai_router.stt_adapter.stt", lambda: _EmptySTT())
    async with SessionFactory() as s:
        user = await _make_premium(s, 8801)  # even a Premium user is blocked
        await feature_flags.set_flag(s, "voice_input", False)
        msg = _Msg()
        await chat.on_voice(msg, s, user, _tr)
        # coming_soon shown; STT never reached (would have yielded voice_in.empty).
        assert msg.answers == ["voice_in.coming_soon"]


async def test_free_user_blocked_by_default(monkeypatch):
    monkeypatch.setattr("core.ai_router.stt_adapter.stt", lambda: _EmptySTT())
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 8802)  # free user, default flags
        msg = _Msg()
        await chat.on_voice(msg, s, user, _tr)
        assert msg.answers == ["gate.premium_voice"]


async def test_free_user_allowed_when_admin_opens_it(monkeypatch):
    monkeypatch.setattr("core.ai_router.stt_adapter.stt", lambda: _EmptySTT())
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 8803)  # free user
        await feature_flags.set_flag(s, "voice_input_free", True)
        msg = _Msg()
        await chat.on_voice(msg, s, user, _tr)
        # Passed both gates → reached STT (empty transcript branch).
        assert msg.answers == ["voice_in.empty"]


async def test_premium_user_allowed_by_default(monkeypatch):
    monkeypatch.setattr("core.ai_router.stt_adapter.stt", lambda: _EmptySTT())
    async with SessionFactory() as s:
        user = await _make_premium(s, 8804)
        msg = _Msg()
        await chat.on_voice(msg, s, user, _tr)
        assert msg.answers == ["voice_in.empty"]  # reached STT, no gate hit


async def test_banned_user_blocked(monkeypatch):
    monkeypatch.setattr("core.ai_router.stt_adapter.stt", lambda: _EmptySTT())
    async with SessionFactory() as s:
        user = await _make_premium(s, 8805)  # premium but banned
        user.is_banned = True
        await s.commit()
        msg = _Msg()
        await chat.on_voice(msg, s, user, _tr)
        assert msg.answers == ["common.banned"]  # blocked before any gate/STT


async def test_stt_unavailable_reports_coming_soon(monkeypatch):
    monkeypatch.setattr("core.ai_router.stt_adapter.stt", lambda: _UnavailableSTT())
    async with SessionFactory() as s:
        user = await _make_premium(s, 8806)
        msg = _Msg()
        await chat.on_voice(msg, s, user, _tr)
        assert msg.answers == ["voice_in.coming_soon"]  # STT provider not configured


async def test_stt_error_reports_failed(monkeypatch):
    monkeypatch.setattr("core.ai_router.stt_adapter.stt", lambda: _BrokenSTT())
    async with SessionFactory() as s:
        user = await _make_premium(s, 8807)
        msg = _Msg()
        await chat.on_voice(msg, s, user, _tr)
        assert msg.answers == ["voice_in.failed"]  # unexpected STT failure
