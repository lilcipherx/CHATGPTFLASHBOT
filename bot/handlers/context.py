"""/deletecontext (§15.10) — clears the rolling Redis context for the user."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from core.i18n import Translator
from core.models import User
from core.services.context import clear_context

router = Router()


@router.message(Command("deletecontext"))
async def cmd_deletecontext(message: Message, user: User, _: Translator) -> None:
    await clear_context(user.user_id)
    await message.answer(_("deletecontext.done"))
