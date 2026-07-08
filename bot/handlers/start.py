"""/start, the persistent 'Home' button, and the generic 'close' callback.

Deep-link referral capture: /start ref_<user_id> writes users.referred_by for
brand-new users only (self-referral guarded in the users service)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import onboarding_language_keyboard
from bot.keyboards.reply import main_menu
from bot.states import MainSG
from core.config import settings
from core.constants import LANGUAGES
from core.i18n import Translator
from core.models import User
from core.services.users import set_language

router = Router()


def _parse_ref(command: CommandObject | None) -> int | None:
    if command and command.args and command.args.startswith("ref_"):
        try:
            return int(command.args[4:])
        except ValueError:
            return None
    return None


def _parse_source(command: CommandObject | None) -> str | None:
    """Traffic-source token from the /start deep-link payload (ТЗ §7).

    A referral (``ref_<id>``) or gift-redeem (``redeem_<code>``) payload is NOT a
    traffic source. Any other payload is treated as the source: an explicit
    ``src_<token>`` convention has its prefix stripped; a bare payload is used
    verbatim. Returns None for no/blank/ref/redeem payload.
    """
    if not (command and command.args):
        return None
    arg = command.args.strip()
    if not arg or arg.startswith(("ref_", "redeem_", "promo_")):
        return None
    if arg.startswith("src_"):
        arg = arg[4:]
    arg = arg.strip()
    return arg[:64] if arg else None


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    created: bool,
    _: Translator,
) -> None:
    if user.is_banned:
        await message.answer(_("common.banned"))
        return

    # First-touch traffic attribution (ТЗ §7): set the source once, for brand-new
    # users only. The user row is created in middleware before this handler runs,
    # so we stamp the source here; never overwrite an existing value.
    if created and user.source is None:
        src = _parse_source(command)
        if src:
            user.source = src
            await session.commit()

    # Welcome bonus (ТЗ §4): the ✨ was granted at signup (get_or_create_user); tell the
    # new user so the grant is visible rather than silently landing in the balance.
    if created:
        from core.services import pricing

        wb = (await pricing.promos(session)).get("welcome_bonus", 0)
        if wb > 0:
            await message.answer(_("promo.welcome_bonus", amount=wb))

    ref = _parse_ref(command)
    if created and ref and ref != user.user_id and user.referred_by is None:
        from core.services.referrals import (
            can_attribute_invite,
            grant_invitee_welcome,
            notify_referrer,
            reward_referral_on_register,
        )

        # Honour the admin referral on/off switch + daily per-referrer invite cap.
        if await can_attribute_invite(session, ref):
            user.referred_by = ref
            await session.commit()
            # Two-sided: give the INVITED user their welcome ✨ (if enabled).
            welcome = await grant_invitee_welcome(session, user)
            if welcome:
                await message.answer(_("ref.welcome_bonus", amount=welcome))
            # Reward the referrer for the registration. If a channel gate requires
            # subscription, this is withheld now and retried when the user passes
            # the gate (see handlers/misc.cb_gate_check).
            rewarded = await reward_referral_on_register(session, message.bot, user)
            if rewarded:
                await notify_referrer(*rewarded)

    # Gift-redeem deep-link: /start redeem_<code> — the link the gift-purchased
    # message advertises (gift.py). Redeem here, then fall through to the welcome.
    # (Without this the payload would just be ignored and the gift never claimed.)
    arg = (command.args or "").strip()
    if arg.startswith("redeem_"):
        code = arg[len("redeem_"):].strip()
        if code:
            from core.services import gifts

            _ok, text = await gifts.redeem_gift(session, code, user)
            await message.answer(text)

    # Promo deep-link: /start promo_<CODE> — the share/QR link the admin panel
    # generates. Redeems the code via the same race-safe path as /promo, then falls
    # through to the welcome. (Without this the payload would be ignored.)
    if arg.startswith("promo_"):
        pcode = arg[len("promo_"):].strip()
        if pcode:
            from core.services import promos

            res = await promos.redeem(session, user, pcode)
            if res.status == "already":
                await message.answer(_("promo.already"))
            elif res.status == "not_eligible":
                await message.answer(_("promo.not_eligible"))
            elif res.status == "applied":
                await message.answer(_("promo.applied", percent=res.amount))
            elif not res.ok:
                await message.answer(_("promo.invalid"))
            else:
                from bot.handlers.promo import reward_label

                await message.answer(
                    _("promo.ok", amount=res.amount, reward=reward_label(_, res.reward_type))
                )

    await state.set_state(MainSG.idle)

    # First run: ask the user to confirm their language explicitly, so we store an
    # accurate, chosen value (Telegram's auto-detected language is only a default).
    # The welcome is sent once they pick one (cb_onboarding_lang). Returning users
    # already have a language, so they skip straight to the welcome.
    if created:
        await message.answer(
            _("settings.lang.choose"), reply_markup=onboarding_language_keyboard()
        )
        return

    await _send_welcome(message, session, _)


async def _send_welcome(message: Message, session: AsyncSession, _: Translator) -> None:
    """Branded media (optional) + the localized welcome with the main menu."""
    await _send_welcome_media(message, session)
    await message.answer(
        _("start.welcome", support=settings.support_contact),
        reply_markup=main_menu(_),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("onblang:"))
async def cb_onboarding_lang(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    """First-run language choice → store it, then show the welcome in that language."""
    code = (callback.data or "").split(":", 1)[1]
    if code not in dict(LANGUAGES):
        await callback.answer()
        return
    await set_language(session, user, code)
    new_t = Translator(code)

    # Localize the Telegram command-bar for this chat (best-effort).
    try:
        from aiogram.types import BotCommandScopeChat

        from bot.main import commands_for

        await callback.bot.set_my_commands(
            commands_for(code), scope=BotCommandScopeChat(chat_id=callback.message.chat.id)
        )
    except Exception:  # noqa: BLE001 — command-bar localization is best-effort
        pass

    await callback.answer()
    # Replace the picker with the welcome (delete is best-effort — a too-old message
    # can't be deleted, in which case the welcome simply follows it).
    try:
        await callback.message.delete()
    except Exception:  # noqa: BLE001
        pass
    await state.set_state(MainSG.idle)
    await _send_welcome(callback.message, session, new_t)


async def _send_welcome_media(message: Message, session: AsyncSession) -> None:
    """Optional branded media at the top of /start (ТЗ §1/§3). Best-effort: a bad
    URL/type must NEVER break /start — on any failure we silently fall back to the
    text-only welcome that always follows."""
    from core.services import pricing

    try:
        brand = await pricing.branding(session)
        url = brand["start_media_url"]
        if not url:
            return
        if brand["start_media_type"] == "video":
            await message.answer_video(url)
        else:
            await message.answer_photo(url)
    except Exception:  # noqa: BLE001 — media is decorative; never block the welcome
        pass


# FIX: AUDIT-116 - btn_home removed (dead code, btn.home key missing from locales)

@router.callback_query(F.data == "close")
async def cb_close(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.delete()
    await callback.answer()
