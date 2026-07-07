"""/support <text> — file a message to the admin support inbox (ТЗ §7).

The message is stored as an inbound SupportMessage that surfaces in the admin
panel's open inbox; the admin can reply from there (delivered back via the bot).
Banned users are already stopped by BanMiddleware, but we re-check defensively so
the handler is safe to call in isolation.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n import Translator
from core.models import User
from core.services import support

router = Router()


@router.message(Command("support"))
async def cmd_support(
    message: Message, command: CommandObject, session: AsyncSession, user: User,
    _: Translator,
) -> None:
    if user.is_banned:
        return
    text = (command.args or "").strip()
    if not text:
        await message.answer(_("support.usage"))
        return
    await support.record_inbound(session, user.user_id, text)
    await message.answer(_("support.sent"))
