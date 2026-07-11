"""Ban enforcement middleware — single source of truth.

A banned user must be blocked from EVERY interaction (chat, photo/video/music
generation, search, payments…), not just the handful of handlers that happened
to check `user.is_banned` themselves. Registered after UserContextMiddleware so
`data["user"]` is populated; runs before the channel gate / handlers.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, TelegramObject  # FIX: B5

from core.i18n import Translator


class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # FIX: AUDIT-P6 - a successful_payment service message must ALWAYS reach its
        # handler: Telegram already charged the user (pre_checkout answered ok=True), so
        # dropping it here — if the user got banned between pre-checkout and delivery —
        # would take the money without crediting. ThrottlingMiddleware carves this out
        # identically. No other event type carries this attribute, so a plain getattr is
        # both sufficient and safe.
        if getattr(event, "successful_payment", None) is not None:
            return await handler(event, data)

        user = data.get("user")
        if user is None or not user.is_banned:
            return await handler(event, data)

        # Banned → notify and stop the pipeline.
        _ = data.get("_") or Translator(getattr(user, "language_code", "ru"))
        if isinstance(event, Message):
            await event.answer(_("common.banned"))
        elif isinstance(event, CallbackQuery):
            await event.answer(_("common.banned"), show_alert=True)
        elif isinstance(event, PreCheckoutQuery):  # FIX: B5 - reject Stars payments from banned users
            await event.answer(ok=False, error_message=_("common.banned"))
        return None
