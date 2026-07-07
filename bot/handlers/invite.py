"""/invite (ТЗ §3): the user's referral deep-link + how many they've invited.

The link is ``https://t.me/<botusername>?start=ref_<user_id>`` — the same payload
/start parses to set ``referred_by``. The invite count reuses the referrals service
so it stays consistent with reward attribution; the per-invite reward is read live
from pricing so an admin change is reflected here without a redeploy.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n import Translator
from core.models import User
from core.services import referrals

router = Router()


async def invite_summary(session: AsyncSession, user: User) -> dict:
    """Pure-ish data for /invite: the link suffix (uses user_id) + invite count.

    Keeps the Bot (needed only for the username) out, so the count is unit-testable
    without a live Bot.
    """
    return {
        "link_suffix": f"ref_{user.user_id}",
        "count": await referrals.count_referrals(session, user.user_id),
        "earned": await referrals.total_earned(session, user.user_id),
    }


@router.message(Command("invite", "ref"))
async def cmd_invite(
    message: Message, session: AsyncSession, user: User, _: Translator
) -> None:
    if user.is_banned:
        await message.answer(_("common.banned"))
        return

    summary = await invite_summary(session, user)
    me = await message.bot.get_me()
    link = f"https://t.me/{me.username}?start={summary['link_suffix']}"
    # Show the SAME reward the referral service actually grants (reward_credits from
    # the referral settings), so the advertised amount can never diverge from what
    # the user receives. (The legacy pricing.referral_reward key is no longer used.)
    reward = (await referrals.get_settings(session))["reward_credits"]

    await message.answer(
        _("invite.summary", link=link, count=summary["count"], reward=reward,
          earned=summary["earned"]),
        disable_web_page_preview=True,
    )
