"""The 🔊 voice (TTS) reply button is admin-gated by the ``voice_output`` flag.

When the admin turns it off, the button must not be rendered under AI replies (and
the handler refuses stale buttons — covered by the flag check in cb_voice)."""
from __future__ import annotations

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
