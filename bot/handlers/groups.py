"""Работа в группах (ТЗ §3): в group/supergroup бот отвечает ТОЛЬКО когда к нему
обратились — @упоминанием или reply на его сообщение — и только если админ включил
флаг groups_enabled. Иначе молчит, чтобы не реагировать на любой чат группы."""
from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.chat import _answer_text
from core.i18n import Translator
from core.models import User
from core.services import pricing

router = Router()


def is_addressed(text: str, bot_username: str, reply_to_bot: bool) -> bool:
    """К боту обратились? True если reply на его сообщение ИЛИ в тексте есть
    @username бота (регистронезависимо)."""
    if reply_to_bot:
        return True
    if not bot_username:
        return False
    return f"@{bot_username}".lower() in (text or "").lower()


def strip_mention(text: str, bot_username: str) -> str:
    """Убирает @username бота из текста (регистронезависимо) и обрезает пробелы."""
    if not bot_username:
        return (text or "").strip()
    cleaned = re.sub(rf"@{re.escape(bot_username)}", "", text or "", flags=re.IGNORECASE)
    return cleaned.strip()


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def on_group_text(
    message: Message, session: AsyncSession, user: User, _: Translator
) -> None:
    """Текст в группе: отвечаем только если к боту обратились и groups_enabled."""
    try:
        # bot.me() is cached per-Bot by aiogram, so this is cheap AND correct under
        # multi-bot (each receiving Bot resolves its OWN username/id — a module-level
        # cache would pin the first bot's username and mis-handle a second bot's @mention).
        me = await message.bot.me()
        bot_username = me.username or ""
        reply_to_bot = bool(
            message.reply_to_message
            and message.reply_to_message.from_user
            and message.reply_to_message.from_user.id == me.id
        )
        if not is_addressed(message.text or "", bot_username, reply_to_bot):
            return  # случайный чат группы — молчим

        if not (await pricing.chat_config(session))["groups_enabled"]:
            return  # админ выключил ответы в группах

        text = strip_mention(message.text or "", bot_username)
        if not text:
            return  # обратились без вопроса — отвечать нечем

        await _answer_text(message, session, user, _, text)
    except Exception as exc:  # noqa: BLE001 — групповой ответ best-effort, не валим апдейт
        # FIX: AUDIT-12 - log + fallback message instead of silent pass
        import structlog
        structlog.get_logger().warning(
            "groups.answer_failed", chat_id=message.chat.id, error=str(exc))
        try:
            await message.answer(_("ai.unavailable"))
        except Exception:
            pass
