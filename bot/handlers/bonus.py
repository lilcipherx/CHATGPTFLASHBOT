"""Daily login-streak bonus — /bonus command + the inline «🎁 Бонус» button."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n import Translator
from core.models import User
from core.services import daily_bonus

router = Router()


def _text(_: Translator, res) -> str:
    if res.already_today:
        return _("bonus.already", streak=res.streak)
    return _("bonus.claimed", amount=res.amount, streak=res.streak)


@router.message(Command("bonus", "daily"))
async def cmd_bonus(message: Message, session: AsyncSession, user: User, _: Translator) -> None:
    res = await daily_bonus.claim(session, user)
    await message.answer(_text(_, res))


@router.callback_query(F.data == "bonus:claim")
async def cb_bonus(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    res = await daily_bonus.claim(session, user)
    await callback.answer(_text(_, res), show_alert=True)
