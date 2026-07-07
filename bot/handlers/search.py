"""/s — internet search (§3.2). Counted in the weekly text quota.

Flow: /s (or the «Интернет поиск» button) shows the search intro (with a model
picker when the admin has enabled search models) and waits for a query; the next
message is searched. `/s <query>` also works directly.

The search MODEL is admin-controlled: the admin ticks `search` on models in the
AI-routing catalog, the user picks one here, and the query is routed to it (real
web access lives in the upstream id — Perplexity Sonar, an OpenAI *-search-preview
model, an OpenRouter ":online" variant). Falls back to Perplexity → the user's text
model so /s always answers even before a search model is configured."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.format_md import split_text
from bot.keyboards.inline import account_keyboard, search_model_keyboard
from bot.states import SearchSG
from core.ai_router.search_adapter import resolve_search_model, run_search
from core.i18n import Translator, all_labels
from core.models import User
from core.services import pricing
from core.services.ai_routing import enabled_search_models
from core.services.moderation import moderate
from core.services.quota import QuotaExceeded, consume_text, refund_text
from core.services.users import set_search_model

router = Router()


async def _intro_markup(
    session: AsyncSession, user: User, _: Translator
) -> InlineKeyboardMarkup | None:
    """A one-button keyboard opening the search-model picker, showing the current
    model — but only when the admin has enabled ≥1 search model. None otherwise, so
    the intro stays clean when the feature isn't configured."""
    models = await enabled_search_models(session)
    if not models:
        return None
    # FIX: SEARCH-6 - reuse the list just fetched instead of re-querying inside resolve.
    current = await resolve_search_model(session, user, models)
    name = current.title if current else models[0].title
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text=_("btn.search_model", name=name), callback_data="searchmodel:open")
    b.adjust(1)
    return b.as_markup()


async def _do_search(
    message: Message, query: str, session: AsyncSession, user: User, _: Translator
) -> None:
    # Moderate the query before charging (mirrors the chat handler's policy).
    mod = await moderate(query)
    if not mod.allowed:
        await message.answer(_("mod.blocked"))
        return
    try:
        qstate = await consume_text(session, user)
    except QuotaExceeded as exc:
        key = "quota.exceeded.premium" if exc.state.is_premium else "quota.exceeded.free"
        await message.answer(
            _(key, used=exc.state.used, limit=exc.state.limit),
            reply_markup=account_keyboard(_),
        )
        return
    wait = await message.answer(_("common.please_wait"))
    system = await pricing.search_system_prompt(session)
    # FIX: B1 - wrap the search call in try/except Exception. The dispatcher may raise
    # RateLimitError / APITimeoutError / APIConnectionError / InternalServerError (via
    # the OpenAI SDK) on 429/timeout/network/5xx — none of which are ProviderUnavailable.
    # Without this catch the exception propagates past the `if not result.ok` guard,
    # leaving the user charged with no refund and no result.
    try:
        result = await run_search(session, user, query, system, user.language_code)
    except Exception:  # noqa: BLE001 — any provider failure → refund + surface error
        await refund_text(session, user, credits_charged=qstate.credits_charged,
                          was_premium=qstate.is_premium)  # FIX: B9 - pass was_premium
        await wait.edit_text(_("ai.unavailable"), parse_mode=None)
        return
    # Provider down / rate-limited → return the consumed quota (mirrors chat).
    if not result.ok:
        await refund_text(session, user, credits_charged=qstate.credits_charged,
                          was_premium=qstate.is_premium)  # FIX: B9 - pass was_premium
        # parse_mode=None: the provider error/fallback text is raw and may contain
        # characters the HTML parser rejects (mirrors chat/documents failure paths).
        await wait.edit_text(result.text, parse_mode=None)
        return
    # Deliver in ≤4096-char chunks (search answers with citations are often long):
    # the first replaces the "please wait" message, the rest are new messages.
    parts = split_text(result.text or _("search.nothing"))
    await wait.edit_text(parts[0], disable_web_page_preview=False)
    for part in parts[1:]:
        await wait.answer(part, disable_web_page_preview=False)


@router.message(Command("s", "search"))
async def cmd_search(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    _: Translator,
) -> None:
    sec = await pricing.section_state(session, "search")
    if not sec["enabled"]:
        await message.answer(sec["soon"])
        return
    query = (command.args or "").strip()
    if query:
        await _do_search(message, query, session, user, _)
        return
    await state.set_state(SearchSG.waiting_query)
    await message.answer(
        _("search.intro"), reply_markup=await _intro_markup(session, user, _)
    )


@router.message(F.text.in_(all_labels("btn.search")))
async def btn_search(
    message: Message, state: FSMContext, session: AsyncSession, user: User, _: Translator
) -> None:
    sec = await pricing.section_state(session, "search")
    if not sec["enabled"]:
        await message.answer(sec["soon"])
        return
    await state.set_state(SearchSG.waiting_query)
    await message.answer(
        _("search.intro"), reply_markup=await _intro_markup(session, user, _)
    )


@router.callback_query(F.data == "searchmodel:open")
async def cb_search_model_open(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    """Open the search-model picker (from the intro button)."""
    await callback.answer()
    models = await enabled_search_models(session)
    if not models:
        return
    current = await resolve_search_model(session, user, models)  # FIX: SEARCH-6 - reuse list
    items = [(m.key, m.title) for m in models]
    premium_keys = {m.key for m in models if m.premium}
    await callback.message.edit_text(
        _("search.choose_model"),
        reply_markup=search_model_keyboard(
            _, current.key if current else None, items, premium_keys),
    )


@router.callback_query(F.data.startswith("searchmodel:"))
async def cb_search_model_pick(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    """Select a search model (validated against the live enabled list)."""
    key = callback.data.split(":", 1)[1]
    models = {m.key: m for m in await enabled_search_models(session)}
    model = models.get(key)
    if model is None:
        await callback.answer()
        return
    if model.premium and not user.is_premium:
        await callback.answer(_("model.premium_locked", name=model.title), show_alert=True)
        return
    await set_search_model(session, user, key)
    # Return to the search intro so the user can now type the query.
    await callback.message.edit_text(
        _("search.intro"), reply_markup=await _intro_markup(session, user, _)
    )
    await callback.answer(_("search.model_set", name=model.title))


@router.message(SearchSG.waiting_query, F.text & ~F.text.startswith("/"))
async def on_search_query(
    message: Message, state: FSMContext, session: AsyncSession, user: User, _: Translator
) -> None:
    await state.clear()
    await _do_search(message, message.text, session, user, _)
