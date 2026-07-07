"""/s — internet search (§3.2). Counted in the weekly text quota.

Flow: /s (or the «Интернет поиск» button) shows the search intro and waits for a
query; the next message is searched. `/s <query>` also works directly. Uses
Perplexity when available, otherwise falls back to the user's text model so the
command always produces an answer."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.format_md import split_text
from bot.keyboards.inline import account_keyboard
from bot.states import SearchSG
from core.ai_router import chat as ai_chat
from core.ai_router.base import ProviderUnavailable
from core.ai_router.perplexity_adapter import search as perplexity_search
from core.i18n import Translator, all_labels
from core.models import User
from core.services import pricing
from core.services.moderation import moderate
from core.services.quota import QuotaExceeded, consume_text, refund_text

router = Router()


async def _run_search(query: str, model_key: str, system: str, locale: str = "ru"):
    try:
        return await perplexity_search(query)
    except ProviderUnavailable:
        # graceful fallback to the user's text model, using the admin-editable prompt
        return await ai_chat(model_key, query, system=system, locale=locale)


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
    # FIX: B1 - wrap _run_search in try/except Exception. _run_search only catches
    # ProviderUnavailable; Perplexity via the OpenAI SDK raises RateLimitError /
    # APITimeoutError / APIConnectionError / InternalServerError on 429/timeout/network/
    # 5xx — none of which are ProviderUnavailable. Without this catch the exception
    # propagates past the `if not result.ok: refund_text(...)` guard, leaving the user
    # charged with no refund and no result.
    try:
        result = await _run_search(query, user.selected_model, system, user.language_code)
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
    await message.answer(_("search.intro"))


@router.message(F.text.in_(all_labels("btn.search")))
async def btn_search(
    message: Message, state: FSMContext, session: AsyncSession, _: Translator
) -> None:
    sec = await pricing.section_state(session, "search")
    if not sec["enabled"]:
        await message.answer(sec["soon"])
        return
    await state.set_state(SearchSG.waiting_query)
    await message.answer(_("search.intro"))


@router.message(SearchSG.waiting_query, F.text & ~F.text.startswith("/"))
async def on_search_query(
    message: Message, state: FSMContext, session: AsyncSession, user: User, _: Translator
) -> None:
    await state.clear()
    await _do_search(message, message.text, session, user, _)
