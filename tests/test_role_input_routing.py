"""Custom-role prompt routing (regression for an FSM bug).

``role_received`` runs while the bot waits for a custom-role reply
(``SettingsSG.role_input``). It used to match EVERY message, so a navigation
command typed to leave the prompt (``/photo``, ``/video``, …) was swallowed and
saved as the user's AI role, and a non-text message saved an empty role. The
handler now carries a magic filter that:

  * matches plain role text,
  * still matches the ``/clear`` sentinel (which clears the role here),
  * does NOT match other commands (they escape to their own handlers),
  * does NOT match non-text messages.

We evaluate the handler's actual magic filter directly, so the test pins the
routing without exercising the FSM context.
"""
from __future__ import annotations

from types import SimpleNamespace

from magic_filter import MagicFilter

from bot.handlers import settings as settings_h


def _role_magic() -> MagicFilter:
    for handler in settings_h.router.message.handlers:
        if handler.callback.__name__ == "role_received":
            for f in handler.filters:
                magic = getattr(f, "magic", None)
                if isinstance(magic, MagicFilter):
                    return magic
    raise AssertionError("role_received magic filter not found")


def _matches(text: str | None) -> bool:
    return bool(_role_magic().resolve(SimpleNamespace(text=text)))


def test_plain_text_is_captured_as_role():
    assert _matches("вежливый помощник") is True
    assert _matches("-") is True       # documented clear sentinel
    assert _matches("—") is True  # em dash clear sentinel


def test_clear_command_sentinel_is_captured():
    # "/clear" is the one command kept so it can clear the role.
    assert _matches("/clear") is True


def test_navigation_commands_escape_the_prompt():
    # These commands must fall through to their own handlers, not be saved as a role.
    for cmd in ("/photo", "/video", "/music", "/report", "/start", "/settings"):
        assert _matches(cmd) is False, cmd


def test_non_text_message_is_ignored():
    # A photo/sticker/voice (text=None) must not be saved as an empty role.
    assert _matches(None) is False
