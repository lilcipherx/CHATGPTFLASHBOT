"""/help, /privacy and the channel-gate re-check callback."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.i18n import Translator, all_labels
from core.models import User
from core.services import gate

router = Router()


@router.callback_query(F.data == "gate:check")
async def cb_gate_check(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    await gate.clear_cache(user.user_id)
    ok = await gate.is_subscribed(callback.bot, user.user_id, session)
    if ok:
        # The user just proved channel membership → release any pending referral
        # registration reward that was withheld pending subscription (anti-fraud).
        from core.services.referrals import notify_referrer, reward_referral_on_register

        rewarded = await reward_referral_on_register(session, callback.bot, user)
        if rewarded:
            await notify_referrer(*rewarded)
        if callback.message:
            await callback.message.delete()
        await callback.answer(_("gate.ok"), show_alert=True)
    else:
        await callback.answer(_("gate.not_subscribed"), show_alert=True)


@router.message(F.text.in_(all_labels("btn.translate")))
async def btn_translate(message: Message, _: Translator) -> None:
    # The persistent button hints; actual translation is the 🌐 button under replies.
    await message.answer(_("btn.translate_hint"))


@router.message(Command("help"))
async def cmd_help(message: Message, _: Translator) -> None:
    await message.answer(
        _("help", support=settings.support_contact), disable_web_page_preview=True
    )


@router.message(Command("privacy"))
async def cmd_privacy(message: Message, _: Translator) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=_("privacy.btn_terms"),
                url="https://teletype.in/@gpt4telegrambot/license-agreement-ru",
            )],
            [InlineKeyboardButton(
                text=_("privacy.btn_policy"),
                url="https://telegram.org/privacy-tpa",
            )],
        ]
    )
    await message.answer(_("privacy"), reply_markup=kb, disable_web_page_preview=True)
