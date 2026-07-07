"""Persistent reply keyboard — the 8 owner-specified buttons.

FIX: AUDIT12-F7 - removed the "Open Mini App" WebApp button from the reply
keyboard. It was the only non-text button and the owner wants a pure-text menu.
The Mini App is still reachable via /start inline button and the bot's web_app
URL — just not on the persistent bottom keyboard anymore.
"""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from core.i18n import Translator


def main_menu(_: Translator) -> ReplyKeyboardMarkup:
    """Pure-text reply keyboard (no WebApp / Mini App button).

    Two-column layout of the 8 standard quick-action buttons. resize_keyboard
    keeps the buttons compact; is_persistent pins the menu so it doesn't
    collapse after the user taps a command.
    """
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=_("btn.model")),     KeyboardButton(text=_("btn.images"))],
        [KeyboardButton(text=_("btn.search")),    KeyboardButton(text=_("btn.video"))],
        [KeyboardButton(text=_("btn.documents")), KeyboardButton(text=_("btn.music"))],
        [KeyboardButton(text=_("btn.premium")),   KeyboardButton(text=_("btn.account"))],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)
