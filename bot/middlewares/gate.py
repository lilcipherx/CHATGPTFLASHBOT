"""Gate #1 middleware — force channel subscription for free users (§24C, §30).

Only active when the `channel_gate` feature flag is on. Admins and premium users
pass freely, as do a small allow-list of commands/callbacks so a gated user can
still subscribe, check, or upgrade. Everything else is blocked with the gate card.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, TelegramObject  # FIX: B7

from bot.keyboards.inline import gate_keyboard
from core.config import settings
from core.i18n import Translator
from core.services import feature_flags, gate

# Commands / callbacks a gated user may still use (to subscribe or pay).
_ALLOW_COMMANDS = {"/start", "/premium", "/account", "/privacy", "/help"}
_ALLOW_CB_PREFIXES = ("gate:", "premium:", "prem:", "premdur:", "pay:", "close")


def _allowed(event: TelegramObject) -> bool:
    if isinstance(event, Message):
        # Strip args and the @botusername suffix groups add (/start@MyBot).
        token = (event.text or "").split(maxsplit=1)[0] if event.text else ""
        command = token.split("@", 1)[0]
        return command in _ALLOW_COMMANDS
    if isinstance(event, CallbackQuery):
        data = event.data or ""
        # FIX: AUDIT-170 - exact match for colon-less entries, prefix for colon entries
        return any(data == p if ":" not in p else data.startswith(p) for p in _ALLOW_CB_PREFIXES)
    return False


class ChannelGateMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("user")
        session = data.get("session")
        if user is None or session is None:
            return await handler(event, data)
        if user.user_id in settings.admin_ids or user.is_premium:
            return await handler(event, data)
        if not await feature_flags.is_enabled_cached(session, "channel_gate"):
            return await handler(event, data)
        if _allowed(event):
            return await handler(event, data)

        bot = getattr(event, "bot", None) or data.get("bot")
        if bot and await gate.is_subscribed(bot, user.user_id, session):
            return await handler(event, data)

        # Not subscribed → show the gate card and stop.
        _ = data.get("_") or Translator(user.language_code)
        channels = await gate.active_channels(session)
        markup = gate_keyboard(_, channels)
        if isinstance(event, Message):
            await event.answer(_("gate.channel"), reply_markup=markup)
        elif isinstance(event, CallbackQuery):
            await event.answer()
            if event.message:
                await event.message.answer(_("gate.channel"), reply_markup=markup)
        elif isinstance(event, PreCheckoutQuery):  # FIX: B7 - block payments for non-subscribed users
            await event.answer(ok=False, error_message=_("gate.channel"))
        return None
