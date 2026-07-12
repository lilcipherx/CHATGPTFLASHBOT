"""The 🔊 voice (TTS) reply button is admin-gated by the ``voice_output`` flag.

When the admin turns it off, the button must not be rendered under AI replies (and
the handler refuses stale buttons — covered by the flag check in cb_voice)."""
from __future__ import annotations

import pytest

from bot.handlers import chat
from bot.handlers.chat import _reply_actions
from core.i18n import Translator
from core.services.feature_flags import default_flags


def _buttons(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def test_voice_button_shown_when_enabled():
    _ = Translator("ru")
    data = _buttons(_reply_actions(_, voice=True))
    assert "msg:voice" in data
    assert "msg:translate" in data


def test_voice_button_hidden_when_disabled():
    _ = Translator("ru")
    data = _buttons(_reply_actions(_, voice=False))
    assert "msg:voice" not in data
    # Other actions stay available.
    assert "msg:translate" in data
    assert "fb:up" in data


def test_voice_output_flag_defaults_on():
    assert default_flags()["voice_output"] is True


class _FakeMsg:
    def __init__(self):
        self.chat = type("C", (), {"id": 1})()
        self.message_id = 2
        self.text = "hi"

    async def answer(self, *a, **k):
        return None


class _FakeCallback:
    data = "msg:voice"

    def __init__(self):
        self.message = _FakeMsg()
        self.answered = False

    async def answer(self, *a, **k):
        self.answered = True


@pytest.mark.asyncio
async def test_cb_voice_import_resolves_and_runs(monkeypatch):
    """Regression: cb_voice imported first_seen from core.services.ratelimit, where it
    does NOT exist — an ImportError raised OUTSIDE the try/except, so every tap of the
    🔊 button crashed to the global error handler and the TTS feature was 100% dead.
    Drive the handler past that import (flag OFF → early return) and assert it does not
    raise."""
    async def _flag_off(_session, _name):
        return False

    monkeypatch.setattr(chat.feature_flags, "is_enabled", _flag_off)

    cb = _FakeCallback()
    user = type("U", (), {"is_premium": True, "voice_name": None})()
    # session is unused before the early return; pass a sentinel.
    await chat.cb_voice(cb, session=object(), user=user, _=Translator("ru"))
    assert cb.answered  # reached the flag check → import resolved, handler alive
