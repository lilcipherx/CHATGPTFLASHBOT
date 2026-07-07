"""Inline mode (ТЗ §3): users type `@bot <вопрос>` in any chat and pick the AI
answer. Inline queries don't go through the message/callback middleware path, so
this handler is self-sufficient — it opens its own DB session and resolves the
user via get_or_create_user to honour their selected model. Everything is wrapped
so a failure surfaces as an error article instead of crashing the dispatcher."""
from __future__ import annotations

import logging
import uuid

from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from core.ai_router import chat as ai_chat
from core.constants import DEFAULT_MODEL
from core.db import SessionFactory
from core.i18n import t
from core.services.ratelimit import allow as rl_allow
from core.services.users import get_or_create_user

log = logging.getLogger(__name__)

router = Router()

MIN_QUERY_LEN = 2
CACHE_TIME = 10

# Inline answers are FREE (they don't consume the weekly text quota) and inline
# queries bypass the message/callback throttle middleware entirely, so without a
# limit here a script could spam unmetered, uncharged AI calls via @bot <q>. A
# per-user fixed-window cap (generous enough that real typing is never affected,
# tight enough to stop automated abuse) gates the AI call on a Redis-only check.
INLINE_RL_LIMIT = 20
INLINE_RL_WINDOW = 60


async def build_inline_answer(
    text: str, user_id: int, locale_hint: str = "ru"
) -> tuple[str, str]:
    """Core inline logic, decoupled from the live InlineQuery for testability.

    Returns (article_title, message_text):
      - empty/too-short query → a hint (no AI call);
      - otherwise route through the AI using the user's selected model;
      - a non-ok AI result → an error message.

    `locale_hint` (the Telegram client language) localizes the pre-lookup hint /
    throttle copy without a DB hit; once we look the user up, their STORED locale
    drives the actual answer + error copy.
    """
    query = (text or "").strip()
    if len(query) < MIN_QUERY_LEN:
        return t("inline.hint_title", locale_hint), t("inline.hint_text", locale_hint)

    # Anti-abuse: cap unmetered inline AI calls per user (Redis-only, before the DB
    # lookup or the AI call). Real users never hit this; an automated spammer does.
    if not await rl_allow(f"inline:{user_id}", INLINE_RL_LIMIT, INLINE_RL_WINDOW):
        return (
            t("inline.throttle_title", locale_hint),
            t("inline.throttle_text", locale_hint),
        )

    model = DEFAULT_MODEL
    locale = locale_hint
    try:
        async with SessionFactory() as session:
            user, _ = await get_or_create_user(session, user_id)
            model = user.selected_model
            locale = user.language_code or locale_hint
            # Inline mode bypasses the message/callback middleware chain, so the ban
            # gate (BanMiddleware) never runs here. Enforce it directly — a banned
            # user must be blocked from EVERY surface, including free inline AI.
            if user.is_banned:
                return t("inline.error_title", locale), t("inline.error_text", locale)
    except Exception:  # noqa: BLE001 — DB hiccup must not block an answer
        log.exception("inline: user lookup failed for %s", user_id)

    # FIX: C1 - moderate before the (free, unmetered) AI call. Every other free-text
    # entry point (chat / search / photo / video / music / documents) moderates; inline
    # mode bypassed it, turning @bot <banned-content> into an unmoderated AI call.
    from core.services.moderation import moderate as _moderate
    if not (await _moderate(query)).allowed:
        return t("inline.error_title", locale), t("inline.error_text", locale)

    result = await ai_chat(model, query, locale=locale)
    if not result.ok:
        return t("inline.error_title", locale), t("inline.error_text", locale)
    return query, result.text


@router.inline_query()
async def on_inline_query(inline_query: InlineQuery) -> None:
    locale_hint = inline_query.from_user.language_code or "ru"
    try:
        title, message_text = await build_inline_answer(
            inline_query.query, inline_query.from_user.id, locale_hint
        )
    except Exception:  # noqa: BLE001 — never crash the dispatcher on inline errors
        log.exception("inline: failed to build answer")
        title = t("inline.error_title", locale_hint)
        message_text = t("inline.error_text", locale_hint)

    article = InlineQueryResultArticle(
        id=str(uuid.uuid4()),
        title=title,
        description=message_text[:100],
        input_message_content=InputTextMessageContent(
            message_text=message_text, parse_mode=None
        ),
    )
    await inline_query.answer([article], cache_time=CACHE_TIME, is_personal=True)
