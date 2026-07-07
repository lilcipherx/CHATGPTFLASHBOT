"""Document upload (§5.1) — Premium only, 3 generations per question.

Send a supported file (≤10 MB) → text is extracted and cached for 2h. A caption
is answered immediately; otherwise the user asks follow-up questions in chat
(the active document is injected by the chat handler)."""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.format_md import split_text
from bot.keyboards.inline import account_keyboard
from core.ai_router import chat as ai_chat
from core.i18n import Translator, all_labels
from core.models import User
from core.services import pricing
from core.services.context import set_document
from core.services.documents import (
    MAX_FILE_BYTES,
    SUPPORTED_EXT,
    UnsupportedDocument,
    ext_of,
    extract_text,
)
from core.services.moderation import moderate
from core.services.quota import QuotaExceeded, consume_text, refund_text

router = Router()


@router.message(F.text.in_(all_labels("btn.documents")))
async def btn_documents(message: Message, session: AsyncSession, _: Translator) -> None:
    sec = await pricing.section_state(session, "documents")
    if not sec["enabled"]:
        await message.answer(sec["soon"])
        return
    # The info text itself states the /premium requirement; the gate is enforced
    # on actual file upload (on_document).
    await message.answer(_("docs.prompt"))


@router.message(F.chat.type == "private", F.document)
async def on_document(
    message: Message, session: AsyncSession, user: User, _: Translator
) -> None:
    # Private-only, like the text/photo/voice handlers: in groups the bot must not
    # react to (and charge for) every uploaded file.
    if user.is_banned:
        await message.answer(_("common.banned"))
        return

    sec = await pricing.section_state(session, "documents")
    if not sec["enabled"]:
        await message.answer(sec["soon"])
        return

    if not user.is_premium:
        await message.answer(_("gate.premium"))
        return

    cost = await pricing.document_cost(session)
    doc = message.document
    ext = ext_of(doc.file_name or "")
    if ext not in SUPPORTED_EXT:
        await message.answer(_("doc.unsupported"))
        return
    if doc.file_size and doc.file_size > MAX_FILE_BYTES:
        await message.answer(_("doc.too_large"))
        return

    wait = await message.answer(_("common.please_wait"))

    # FIX: #1 - wrap download+extract in try/except so a download failure (expired
    # file_id, network) or a parser failure (corrupted PDF, malformed xlsx) doesn't
    # leave the user staring at "please wait" forever. Mirrors F1 fix in chat.py.
    try:
        buf = await message.bot.download(doc.file_id)
        data = buf.read()
        text = extract_text(doc.file_name, data)
    except UnsupportedDocument:
        await wait.edit_text(_("doc.extract_failed"))
        return
    except Exception:  # noqa: BLE001 — download or parser failure
        await wait.edit_text(_("doc.extract_failed"))
        return

    if not text:
        await wait.edit_text(_("doc.empty"))
        return

    # FIX: M2 - moderate the extracted document text BEFORE caching it as the chat
    # context. A banned-content document would otherwise sit in Redis for 2h and be
    # re-injected into every follow-up question — bypassing the per-message moderation
    # that guards the question itself. We block here (not on the question) because the
    # document is the larger surface and is shared across turns.
    mod_doc = await moderate(text)
    if not mod_doc.allowed:
        await wait.edit_text(_("mod.blocked"))
        return

    await set_document(user.user_id, doc.file_name, text)

    caption = (message.caption or "").strip()
    if not caption:
        # Escape the user-controlled filename: messages go out as HTML (default
        # parse_mode), and t() interpolates kwargs with str.format WITHOUT escaping,
        # so a name like `data<2024>.pdf` or `<b>x</b>.txt` would inject markup or
        # (a stray "<") make Telegram reject the confirmation with a 400.
        await wait.edit_text(
            _("doc.received", name=html.escape(doc.file_name or ""), cost=cost)
        )
        return

    # Moderate the question before charging (mirrors the chat handler's policy).
    mod = await moderate(caption)
    if not mod.allowed:
        await wait.edit_text(_("mod.blocked"))
        return

    # Caption present → answer immediately and charge the document cost.
    try:
        qstate = await consume_text(session, user, cost=cost)
    except QuotaExceeded as exc:
        await wait.edit_text(
            _("quota.exceeded.premium", used=exc.state.used, limit=exc.state.limit),
            reply_markup=account_keyboard(_),
        )
        return

    prompt = f"Документ «{doc.file_name}»:\n\n{text}\n\nВопрос: {caption}"
    # FIX: AUDIT-12 - wrap ai_chat in try/except so provider raise triggers refund
    try:
        result = await ai_chat(user.selected_model, prompt, locale=user.language_code)
    except Exception:
        await refund_text(session, user, cost, credits_charged=qstate.credits_charged, was_premium=qstate.is_premium)
        await wait.edit_text(_("ai.unavailable"), parse_mode=None)
        return
    # Provider down / rate-limited → return the consumed quota (mirrors chat).
    if not result.ok:
        await refund_text(session, user, cost, credits_charged=qstate.credits_charged,
                          was_premium=qstate.is_premium)  # FIX: B9
        await wait.edit_text(result.text, parse_mode=None)
        return
    # Document answers (summaries etc.) are often long — deliver in ≤4096-char
    # chunks: the first replaces the "please wait" message, the rest follow.
    parts = split_text(result.text)
    await wait.edit_text(parts[0], parse_mode=None)
    for part in parts[1:]:
        await wait.answer(part, parse_mode=None)
