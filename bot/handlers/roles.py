"""Preset roles / personas (ТЗ §3).

A curated, admin-editable list of system-prompt personas the user can switch on
from /roles. Picking one sets `user.custom_role` (+ enables it); the user can turn
it back off. The list itself lives in business_config (core.services.pricing), so
the admin edits personas without a redeploy.
"""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states import SettingsSG
from core.i18n import Translator
from core.models import User
from core.services import pricing
from core.services.users import set_role

router = Router()


async def _roles_keyboard(session: AsyncSession, _: Translator) -> InlineKeyboardMarkup | None:
    roles = await pricing.preset_roles(session)
    if not roles:
        return None
    rows = [[InlineKeyboardButton(text=r["title"], callback_data=f"role:set:{r['key']}")]
            for r in roles]
    # «Write your own» → reuses the /settings role-input FSM, so personas + custom
    # role live behind one /roles surface.
    rows.append([InlineKeyboardButton(text=_("roles.btn_custom"), callback_data="role:custom")])
    rows.append([InlineKeyboardButton(text=_("roles.btn_off"), callback_data="role:off")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text.startswith("/roles"))
async def cmd_roles(
    message: Message, session: AsyncSession, user: User, _: Translator
) -> None:
    if user.is_banned:
        await message.answer(_("common.banned"))
        return
    kb = await _roles_keyboard(session, _)
    if kb is None:
        await message.answer(_("roles.unavailable"))
        return
    head = _("roles.choose")
    if user.role_enabled and user.custom_role:
        head += _("roles.choose_active")
    # Preview each persona with its 1-line description above the buttons, so the user
    # knows what each does before picking. Admin-authored text is HTML-escaped (the bot
    # sends with HTML parse_mode).
    roles = await pricing.preset_roles(session)
    lines = [
        f"• {html.escape(r['title'])} — {html.escape(r['desc'])}"
        for r in roles if r.get("desc")
    ]
    body = head + ("\n\n" + "\n".join(lines) if lines else "")
    await message.answer(body, reply_markup=kb)


@router.callback_query(F.data.startswith("role:set:"))
async def cb_role_set(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    key = callback.data.split(":", 2)[2]
    role = await pricing.preset_role(session, key)
    if role is None:
        await callback.answer(_("roles.not_found"), show_alert=True)
        return
    await set_role(session, user, role["prompt"])
    await callback.answer(_("roles.enabled", title=role["title"]))
    if callback.message:
        await callback.message.answer(_("roles.enabled_full", title=role["title"]))


@router.callback_query(F.data == "role:custom")
async def cb_role_custom(
    callback: CallbackQuery, state: FSMContext, user: User, _: Translator
) -> None:
    """Open the custom-role prompt (same FSM as /settings → role), so the user can
    write their own persona right from /roles."""
    current = (
        _("settings.role.current", role=html.escape(user.custom_role))
        if user.custom_role
        else _("settings.role.current_none")
    )
    await state.set_state(SettingsSG.role_input)
    if callback.message:
        await callback.message.answer(f"{current}\n\n{_('settings.role.prompt')}")
    await callback.answer()


@router.callback_query(F.data == "role:off")
async def cb_role_off(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    await set_role(session, user, None)
    await callback.answer(_("roles.disabled"))
    if callback.message:
        await callback.message.answer(_("roles.disabled_full"))
