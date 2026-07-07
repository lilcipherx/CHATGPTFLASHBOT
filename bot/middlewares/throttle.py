"""Per-user throttling middleware (antifraud). Drops bursts above the window
limit with a gentle notice, using the Redis fixed-window limiter.

Registered as an UPDATE-level *outer* middleware (before the DB session opens —
see bot.main.build_dispatcher), so a flooding user is rejected on a Redis-only
check WITHOUT a Postgres round-trip per spam message. The locale for the notice
comes from the Telegram user's client language, since the DB user isn't loaded
yet at this stage.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from core.i18n import Translator
from core.services.ratelimit import allow
from core.services.throttle_config import get_limits


class ThrottlingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # `event` is an Update here (outer middleware). Only message + callback
        # traffic is throttled, mirroring the previous per-observer registration.
        message = getattr(event, "message", None)
        callback = getattr(event, "callback_query", None)
        # FIX: AUDIT-51 - also handle inline_query, pre_checkout_query, edited_message, shipping_query, poll_answer
        inline_query = getattr(event, "inline_query", None)
        pre_checkout = getattr(event, "pre_checkout_query", None)
        edited = getattr(event, "edited_message", None)
        shipping = getattr(event, "shipping_query", None)
        poll_answer = getattr(event, "poll_answer", None)
        tg_user = None
        if message is not None:
            tg_user = message.from_user
        elif callback is not None:
            tg_user = callback.from_user
        elif inline_query is not None:
            tg_user = inline_query.from_user
        elif pre_checkout is not None:
            tg_user = pre_checkout.from_user
        elif edited is not None:
            tg_user = edited.from_user
        elif shipping is not None:
            tg_user = shipping.from_user
        elif poll_answer is not None:
            tg_user = poll_answer.user

        # FIX: AUDIT13-L15 - NEVER throttle the payment flow. Dropping a pre_checkout_query
        # leaves it unanswered (Telegram fails the payment after ~10s), and dropping a
        # message carrying successful_payment would skip crediting the user (money lost).
        # These are low-volume and must always reach their handlers.
        if pre_checkout is not None or shipping is not None or (
            message is not None and getattr(message, "successful_payment", None) is not None
        ):
            return await handler(event, data)

        limit, window = await get_limits()
        if tg_user is not None:
            # FIX: N5 - Redis-down fail-open: never crash the bot on a throttle check.
            # allow() returns True on Redis errors (see ratelimit.py N4), but we
            # double-guard here so a future regression in allow() cannot take the
            # whole bot down — users see a real answer instead of "Что-то пошло не так".
            try:
                within_limit = await allow(f"throttle:{tg_user.id}", limit, window)
            except Exception:  # noqa: BLE001 — best-effort throttle; never block
                within_limit = True
            if not within_limit:
                _ = Translator(getattr(tg_user, "language_code", None) or "ru")
                text = _("throttle.flood")
                if message is not None:
                    await message.answer(text)
                elif callback is not None:
                    await callback.answer(text, show_alert=False)
                return None  # drop — no DB session was opened for this update
        return await handler(event, data)
