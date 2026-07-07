"""/settings hub (§15.3): model / role / context toggle / voice / language."""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import (
    language_keyboard,
    model_keyboard,
    settings_keyboard,
    voice_keyboard,
)
from bot.keyboards.reply import main_menu
from bot.states import SettingsSG
from core.ai_router.base import ProviderUnavailable
from core.ai_router.tts_adapter import tts
from core.constants import ALL_VOICES, LANGUAGES
from core.i18n import Translator, all_labels
from core.models import User
from core.services.ai_routing import enabled_models
from core.services.users import set_language, set_role, set_voice, toggle_context

router = Router()

# The custom role is the system prompt prepended to EVERY AI request, so an
# unbounded value would inflate token cost on every message and can blow past the
# model's context window. Cap it to a generous limit at the input boundary.
MAX_ROLE_LEN = 1000


@router.message(Command("settings"))
@router.message(F.text.in_(all_labels("btn.settings")))
async def cmd_settings(message: Message, _: Translator) -> None:
    await message.answer(_("settings.intro"), reply_markup=settings_keyboard(_))


@router.callback_query(F.data == "settings:open")
async def cb_settings_open(callback: CallbackQuery, _: Translator) -> None:
    await callback.message.edit_text(_("settings.intro"), reply_markup=settings_keyboard(_))
    await callback.answer()


@router.callback_query(F.data == "settings:model")
async def cb_settings_model(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    # Use the same DB-backed catalog as /model so both surfaces show one set.
    db_models = await enabled_models(session)
    items = [(m.key, m.title) for m in db_models] if db_models else None
    premium_keys = {m.key for m in db_models if m.premium} if db_models else None
    await callback.message.edit_text(
        _("model.intro"),
        reply_markup=model_keyboard(_, user.selected_model, items, premium_keys),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:context")
async def cb_settings_context(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    enabled = await toggle_context(session, user)
    # The settings keyboard is static (no context indicator), so the on/off state
    # is surfaced via the toast only — re-editing to the identical markup would
    # raise Telegram's "message is not modified".
    await callback.answer(_("settings.context.on") if enabled else _("settings.context.off"))


@router.callback_query(F.data == "settings:role")
async def cb_settings_role(
    callback: CallbackQuery, state: FSMContext, user: User, _: Translator
) -> None:
    current = (
        # Escape the user-authored role: messages are sent as HTML and t() does not
        # escape its kwargs, so a role containing "<" (e.g. "reply if x < y") would
        # otherwise be rejected by Telegram with a 400 or inject markup.
        _("settings.role.current", role=html.escape(user.custom_role))
        if user.custom_role
        else _("settings.role.current_none")
    )
    await state.set_state(SettingsSG.role_input)
    await callback.message.answer(f"{current}\n\n{_('settings.role.prompt')}")
    await callback.answer()


# Capture the role text, but let real navigation commands escape the prompt
# (every other state handler excludes commands too — see search/photo/video/music).
# Without this, typing e.g. /photo to leave the role prompt would be swallowed and
# saved as the user's AI role, and a non-text message would save an empty role. The
# "/clear" sentinel is the one command kept, since it clears the role here.
@router.message(
    SettingsSG.role_input,
    F.text & (~F.text.startswith("/") | (F.text == "/clear")),
)
async def role_received(
    message: Message, state: FSMContext, session: AsyncSession, user: User, _: Translator
) -> None:
    text = message.text.strip()
    if text in {"-", "—", "/clear"}:
        await set_role(session, user, None)
        await message.answer(_("settings.role.cleared"))
    elif len(text) > MAX_ROLE_LEN:
        # Reject (don't silently truncate) an oversized prompt so the user knows.
        await message.answer(_("settings.role.too_long", limit=MAX_ROLE_LEN))
        return  # stay in the role-input state so they can re-enter a shorter one
    else:
        # FIX: M1 - moderate the custom role before saving it. The role becomes the
        # system prompt prepended to EVERY subsequent AI request, so an unmoderated
        # role persists across many generations — far worse than a one-shot prompt.
        from core.services.moderation import moderate as _moderate
        if not (await _moderate(text)).allowed:
            await message.answer(_("mod.blocked"))
            await state.clear()
            return
        await set_role(session, user, text)
        await message.answer(_("settings.role.saved"))
    await state.clear()


@router.callback_query(F.data == "settings:voice")
async def cb_settings_voice(callback: CallbackQuery, user: User, _: Translator) -> None:
    if not user.is_premium:
        await callback.answer(_("gate.premium"), show_alert=True)
        return
    await callback.message.edit_text(
        _("settings.voice.intro"),
        reply_markup=voice_keyboard(_, user.voice_name, user.voice_enabled),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("voice:set:"))
async def cb_voice_set(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    voice = callback.data.split(":", 2)[2]
    if voice not in ALL_VOICES:
        await callback.answer()
        return
    # Re-selecting the active voice leaves the keyboard identical → skip the edit to
    # avoid Telegram's "message is not modified".
    if voice == user.voice_name:
        await callback.answer(_("voice.selected", voice=voice))
        return
    await set_voice(session, user, voice=voice)
    await callback.message.edit_reply_markup(
        reply_markup=voice_keyboard(_, voice, user.voice_enabled)
    )
    await callback.answer(_("voice.selected", voice=voice))


@router.callback_query(F.data == "voice:toggle")
async def cb_voice_toggle(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    await set_voice(session, user, enabled=not user.voice_enabled)
    await callback.message.edit_reply_markup(
        reply_markup=voice_keyboard(_, user.voice_name, user.voice_enabled)
    )
    await callback.answer()


@router.callback_query(F.data == "voice:preview")
async def cb_voice_preview(callback: CallbackQuery, user: User, _: Translator) -> None:
    await callback.answer()
    try:
        audio = await tts().speak(_("voice.sample"), voice=user.voice_name)
    except ProviderUnavailable:
        await callback.message.answer(_("tts.unavailable"))
        return
    except Exception:  # noqa: BLE001
        await callback.message.answer(_("tts.failed"))
        return
    from aiogram.types import BufferedInputFile

    await callback.message.answer_voice(BufferedInputFile(audio, filename="preview.ogg"))


@router.message(Command("language"))
async def cmd_language(message: Message, _: Translator) -> None:
    await message.answer(_("settings.lang.choose"), reply_markup=language_keyboard(_))


@router.callback_query(F.data == "settings:lang")
async def cb_settings_lang(callback: CallbackQuery, _: Translator) -> None:
    await callback.message.edit_text(_("settings.lang.choose"), reply_markup=language_keyboard(_))
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("lang:"))
async def cb_lang_set(
    callback: CallbackQuery, session: AsyncSession, user: User
) -> None:
    code = callback.data.split(":", 1)[1]
    if code not in dict(LANGUAGES):
        await callback.answer()
        return
    await set_language(session, user, code)
    new_t = Translator(code)

    # 1) re-render the settings screen in the new language
    await callback.message.edit_text(
        new_t("settings.intro"), reply_markup=settings_keyboard(new_t)
    )
    # 2) refresh the persistent reply keyboard (8 buttons) in the new language
    await callback.message.answer(
        new_t("settings.lang.saved"), reply_markup=main_menu(new_t)
    )
    # 3) localize the Telegram command-bar for this chat
    from aiogram.types import BotCommandScopeChat

    from bot.main import commands_for

    try:
        await callback.bot.set_my_commands(
            commands_for(code), scope=BotCommandScopeChat(chat_id=callback.message.chat.id)
        )
    except Exception:  # noqa: BLE001 — command-bar localization is best-effort
        pass
    await callback.answer(new_t("settings.lang.saved"))
