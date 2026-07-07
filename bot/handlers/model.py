"""/model selector (§15.7) with premium gate (§30A)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import model_keyboard
from core.constants import TEXT_MODELS_BY_KEY
from core.i18n import Translator, all_labels
from core.models import User
from core.services.ai_routing import enabled_models
from core.services.users import set_model

router = Router()


async def _model_meta(session: AsyncSession, key: str) -> tuple[str, bool] | None:
    """Return (title, premium) for a model key from the DB catalog, falling back
    to the static TEXT_MODELS list. None if the key is unknown/disabled."""
    db_models = {m.key: m for m in await enabled_models(session)}
    if key in db_models:
        m = db_models[key]
        return m.title, m.premium
    static = TEXT_MODELS_BY_KEY.get(key)
    return (static.name, static.premium) if static else None


async def _keyboard(session: AsyncSession, _: Translator, active_key: str):
    db_models = await enabled_models(session)
    items = [(m.key, m.title) for m in db_models] if db_models else None
    premium_keys = {m.key for m in db_models if m.premium} if db_models else None
    return model_keyboard(_, active_key, items, premium_keys)


@router.message(Command("model"))
@router.message(F.text.in_(all_labels("btn.model")))
async def cmd_model(
    message: Message, session: AsyncSession, user: User, _: Translator
) -> None:
    await message.answer(
        _("model.intro"), reply_markup=await _keyboard(session, _, user.selected_model)
    )


@router.callback_query(lambda c: c.data and c.data.startswith("model:"))
async def cb_model(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    # FIX: POLISH-12 - answer the callback IMMEDIATELY to close the button spinner.
    # We re-answer with a text payload below for the actual feedback, but the
    # initial empty answer kills the 2-3s "thinking" lag perceived by the user.
    await callback.answer()
    key = callback.data.split(":", 1)[1]
    meta = await _model_meta(session, key)
    if meta is None:
        return
    title, premium = meta

    if premium and not user.is_premium:
        # Re-answer with an alert for the premium-gate message (the first answer
        # was empty; this one shows the popup).
        await callback.answer(_("model.premium_locked", name=title), show_alert=True)
        return

    # Re-selecting the active model leaves the keyboard identical; skip the edit so
    # Telegram doesn't raise "message is not modified".
    if key == user.selected_model:
        await callback.answer(_("model.selected", name=title))
        return

    await set_model(session, user, key)
    await callback.message.edit_reply_markup(
        reply_markup=await _keyboard(session, _, key)
    )
    await callback.answer(_("model.selected", name=title))
