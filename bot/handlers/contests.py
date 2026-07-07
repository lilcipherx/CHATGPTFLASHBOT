"""/contests — list open giveaways and let users enter (ТЗ §7).

Each open contest gets an "Участвовать" inline button; tapping it registers the
user (idempotent — a second tap is acknowledged as "already entered"). Banned
users are blocked upstream by BanMiddleware."""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n import Translator
from core.models import User
from core.services import contests

router = Router()


@router.message(Command("contests"))
async def cmd_contests(message: Message, session: AsyncSession, _: Translator) -> None:
    open_contests = await contests.list_open(session)
    if not open_contests:
        await message.answer(_("contest.none"))
        return
    for c in open_contests:
        count = await contests.entrants_count(session, c.id)
        # Escape the admin-authored title/description: an unescaped '<' or '&' makes
        # Telegram's HTML parser 400 and /contests fails to render for everyone.
        text = f"🎉 <b>{html.escape(c.title)}</b>"
        if c.description:
            text += f"\n\n{html.escape(c.description)}"
        text += "\n\n" + _("contest.entrants", count=count)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text=_("contest.btn_enter"), callback_data=f"contest:enter:{c.id}"
                )
            ]]
        )
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("contest:enter:"))
async def cb_enter(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    try:
        contest_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return

    try:
        newly = await contests.enter(session, contest_id, user.user_id)
    except contests.ContestError:
        await callback.answer(_("contest.ended"), show_alert=True)
        return

    if newly:
        await callback.answer(_("contest.entered"), show_alert=True)
    else:
        await callback.answer(_("contest.already"), show_alert=True)
