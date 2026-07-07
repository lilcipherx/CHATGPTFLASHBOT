"""/promo <code> — redeem a promo code for 🪙 credits or pack credits.

All validation + the atomic, race-safe claim live in core.services.promos; this
handler only parses the command and maps the result to a localized reply.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n import Translator
from core.models import User
from core.services import promos

router = Router()

# Promo reward types that have a localized unit label (promo.reward.<type>); any
# other value is shown verbatim.
_REWARD_TYPES = {"credits", "image", "video", "music", "premium"}


def reward_label(_: Translator, reward_type: str) -> str:
    return _(f"promo.reward.{reward_type}") if reward_type in _REWARD_TYPES else reward_type


@router.message(Command("promo"))
async def cmd_promo(
    message: Message, command: CommandObject, session: AsyncSession,
    user: User, _: Translator,
) -> None:
    if user.is_banned:
        await message.answer(_("common.banned"))
        return
    code = (command.args or "").strip()
    if not code:
        await message.answer(_("promo.usage"))
        return

    result = await promos.redeem(session, user, code)
    if result.status == "already":
        await message.answer(_("promo.already"))
    elif result.status == "not_eligible":
        await message.answer(_("promo.not_eligible"))
    elif result.status == "applied":
        # A discount code — applied to the account, spent on the next purchase.
        await message.answer(_("promo.applied", percent=result.amount))
    elif not result.ok:
        await message.answer(_("promo.invalid"))
    else:
        await message.answer(
            _("promo.ok", amount=result.amount, reward=reward_label(_, result.reward_type))
        )
