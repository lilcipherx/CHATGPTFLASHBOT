"""Bot middlewares: open a DB session per update, then load/create the user and
bind a locale-aware translator. Injected into every handler via kwargs:

    session: AsyncSession
    user:    core.models.User
    _:       core.i18n.Translator   (callable translator bound to user's locale)
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from aiogram.types import User as TgUser

from core.db import SessionFactory
from core.i18n import Translator
from core.services.users import get_or_create_user


class DBSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with SessionFactory() as session:
            data["session"] = session
            return await handler(event, data)


def _extract_tg_user(event: TelegramObject) -> TgUser | None:
    for attr in ("message", "callback_query", "pre_checkout_query"):
        sub = getattr(event, attr, None)
        if sub is not None and getattr(sub, "from_user", None):
            return sub.from_user
    if isinstance(event, Update):
        if event.message:
            return event.message.from_user
        if event.callback_query:
            return event.callback_query.from_user
    return getattr(event, "from_user", None)


class UserContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = _extract_tg_user(event)
        session = data.get("session")
        if tg_user is None or session is None:
            return await handler(event, data)

        # Multi-bot tenant (ТЗ §0): which BotInstance received this update. data["bot"]
        # is the receiving Bot; map its Telegram id to a BotInstance id (None in a
        # single-bot deployment → legacy NULL bot_id). Stamped once at signup.
        from core.services.bots import bot_id_for

        recv_bot = data.get("bot")
        bot_id = bot_id_for(getattr(recv_bot, "id", None)) if recv_bot is not None else None

        user, _created = await get_or_create_user(
            session,
            user_id=tg_user.id,
            username=tg_user.username,
            # Pass Telegram's real language (may be None) — get_or_create_user stores
            # it verbatim; it must not be coerced to a fabricated "ru" here.
            language_code=tg_user.language_code,
            bot_id=bot_id,
        )
        data["user"] = user
        data["created"] = _created
        # Render locale falls back to RU for an unknown/unsupported stored language.
        data["_"] = Translator(user.language_code or "ru")
        return await handler(event, data)
