"""Plain-text AI chat (§3.2) — the catch-all handler.

Flow: ban check → weekly/daily text quota (Gate#1) → rolling context + custom
role → AI router → reply with 🔊(premium)/🌐 action buttons. Context is stored
in Redis (rolling ~1 Q&A pair)."""
from __future__ import annotations

import contextlib
import time

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.format_md import CHUNK_LIMIT as _CHUNK_LIMIT  # noqa: F401 — re-exported for tests
from bot.format_md import TG_LIMIT as TG_MAX
from bot.format_md import render_reply
from bot.format_md import split_text as _split_text
from bot.keyboards.inline import account_keyboard, ad_keyboard
from core.ai_router import chat as ai_chat
from core.ai_router import chat_stream as ai_chat_stream
from core.ai_router.base import ProviderUnavailable
from core.ai_router.image_adapters import generate_image
from core.ai_router.tts_adapter import tts
from core.ai_router.vision import describe_image
from core.i18n import Translator
from core.models import User
from core.services import feature_flags, feedback, packs, pricing, storage
from core.services.context import (
    append_context,
    get_context,
    get_document,
    get_full_reply,
    set_full_reply,
)
from core.services.moderation import moderate
from core.services.quota import QuotaExceeded, consume_text, refund_text

# Service used for in-chat photo editing (img2img). nano_banana (Google) accepts
# image_refs for image-to-image; if its key is unset, run falls back to an honest
# "coming soon" + refund. (ТЗ §3 «редактирование фото в чате»)
PHOTO_EDIT_SERVICE = "nano_banana"
PHOTO_EDIT_COST = 1  # image-pack credits per edit

router = Router()


def _reply_actions(_: Translator, *, voice: bool = True) -> InlineKeyboardMarkup:
    """Action buttons under an AI reply. The 🔊 voice button is shown only when the
    admin ``voice_output`` flag is on (otherwise tapping it would just error)."""
    top = []
    if voice:
        top.append(InlineKeyboardButton(text=_("btn.voice"), callback_data="msg:voice"))
    top.append(InlineKeyboardButton(text=_("btn.translate"), callback_data="msg:translate"))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            top,
            [
                InlineKeyboardButton(text="👍", callback_data="fb:up"),
                InlineKeyboardButton(text="👎", callback_data="fb:down"),
            ],
        ]
    )


async def _send_reply(
    message: Message, md: str, *, markdown: bool, reply_markup=None
) -> None:
    """Render the AI reply per the live markdown toggle and send it, splitting into
    multiple messages when it exceeds Telegram's 4096-char limit. Action buttons go
    on the LAST chunk only. If Telegram rejects our HTML (rare, malformed markup),
    fall back to plain text per chunk so we never lose the answer."""
    parts = _split_text(md)
    last = None
    for i, part in enumerate(parts):
        body, parse_mode = render_reply(part, markdown=markdown)
        kb = reply_markup if i == len(parts) - 1 else None
        try:
            last = await message.answer(body, reply_markup=kb, parse_mode=parse_mode)
        except TelegramBadRequest:
            last = await message.answer(part, reply_markup=kb, parse_mode=None)
    # Chunked reply → stash the full text so translate/voice (buttons on the last
    # message) can act on the WHOLE answer, not just the final chunk.
    if len(parts) > 1 and last is not None:
        await set_full_reply(last.chat.id, last.message_id, md)


async def _maybe_ad(
    message: Message, session: AsyncSession, user: User, _: Translator
) -> None:
    """Free-user ad after a reply (ТЗ §6) — Premium is ad-free. Best-effort.

    Paced by ``user.ad_reply_count``, a dedicated lifetime counter that ticks on every
    free reply here — NOT the quota counter, which stops advancing once the user pays
    from ✨ credits (which would otherwise freeze the ad cadence)."""
    if user.is_premium:
        return
    from core.services import ads

    # FIX: AUDIT-111 - lock user row before increment to prevent lost update
    await session.refresh(user, with_for_update=True)
    user.ad_reply_count = (user.ad_reply_count or 0) + 1
    await session.commit()
    ad = await ads.ad_for_reply(session, user, user.ad_reply_count)
    if ad:
        try:
            await message.answer(ad, parse_mode=None, reply_markup=ad_keyboard(_))
        except Exception:  # noqa: BLE001
            pass


async def _stream_reply(
    message: Message, _: Translator, *, model_key: str, prompt: str,
    system: str | None, history: list[dict] | None, locale: str, markdown: bool,
    voice: bool = True,
) -> tuple[bool, bool, str, bool]:
    """Best-effort streaming reply (ТЗ §3): send a placeholder, then edit it as
    deltas arrive (throttled). Returns (started, ok, full_text, interrupted):
      started=False → nothing was shown; caller falls back to the buffered chat()
      started & ok & not interrupted → final message rendered with markdown + buttons
      started & ok & interrupted → stream broke mid-reply; partial text in full_text.
        Caller should refund the user (they got a truncated answer) but still show
        the partial text so the user isn't left with nothing.
      started & not ok → produced nothing usable; caller refunds + shows error.

    FIX: SKILL-AI3 - added the `interrupted` flag (4-tuple) so the caller can
    distinguish "stream completed normally with a short reply" from "stream broke
    mid-reply and we have a truncated partial". The old 3-tuple conflated them,
    so a valid short reply ("Yes.", "OK.") triggered a false-positive refund.
    """
    placeholder: Message | None = None
    buf: list[str] = []
    started = False
    interrupted = False  # FIX: SKILL-AI3
    last_edit = 0.0
    last_len = 0
    try:
        async for delta in ai_chat_stream(
            model_key, prompt, system=system, history=history, locale=locale
        ):
            buf.append(delta)
            if not started:
                # FIX: X1 - assign placeholder BEFORE flipping started, so a failure in
                # message.answer doesn't leave placeholder=None with started=True →
                # AttributeError on placeholder.edit_text → user charged with no refund.
                placeholder = await message.answer("…")
                started = True
            now = time.monotonic()
            so_far = "".join(buf)
            # Throttle edits: ≥1.2s apart AND ≥30 new chars, to dodge Telegram floods.
            # Stop live edits once the text passes Telegram's 4096 cap (the edit would
            # only error) — the final chunked send below delivers the full answer.
            if (now - last_edit >= 1.2 and len(so_far) - last_len >= 30
                    and len(so_far) <= TG_MAX):
                last_edit, last_len = now, len(so_far)
                try:
                    await placeholder.edit_text(so_far, parse_mode=None)
                except TelegramBadRequest:
                    pass  # "message is not modified" / transient — keep streaming
    except ProviderUnavailable:
        if not started:
            return (False, False, "", False)
        interrupted = True  # FIX: SKILL-AI3 - stream broke after starting
    except Exception:  # noqa: BLE001 — mid-stream failure; deliver whatever arrived
        if not started:
            return (False, False, "", False)
        interrupted = True  # FIX: SKILL-AI3 - stream broke after starting

    full = "".join(buf).strip()
    if not started:
        return (False, False, "", False)
    if not full:
        return (True, False, "", interrupted)
    if interrupted:
        # Stream broke mid-reply — don't try to render the partial as a final
        # message; return it raw so the caller can show it + refund.
        return (True, True, full, True)

    # Deliver in ≤4096-char chunks: the FIRST replaces the streaming placeholder,
    # the rest are new messages; action buttons go on the last chunk only.
    parts = _split_text(full)
    actions = _reply_actions(_, voice=voice)
    first_kb = actions if len(parts) == 1 else None
    body, parse_mode = render_reply(parts[0], markdown=markdown)
    try:
        await placeholder.edit_text(body, parse_mode=parse_mode, reply_markup=first_kb)
    except TelegramBadRequest:
        try:
            await placeholder.edit_text(parts[0], parse_mode=None, reply_markup=first_kb)
        except TelegramBadRequest:
            pass
    last = placeholder
    for i, part in enumerate(parts[1:], start=1):
        kb = actions if i == len(parts) - 1 else None
        body, parse_mode = render_reply(part, markdown=markdown)
        try:
            last = await placeholder.answer(body, parse_mode=parse_mode, reply_markup=kb)
        except TelegramBadRequest:
            last = await placeholder.answer(part, parse_mode=None, reply_markup=kb)
    # Chunked → stash the full text under the last message (see _send_reply).
    if len(parts) > 1 and last is not None:
        await set_full_reply(last.chat.id, last.message_id, full)
    return (True, True, full, False)  # FIX: SKILL-AI3 - 4-tuple, interrupted=False


async def _answer_text(
    message: Message, session: AsyncSession, user: User, _: Translator, text: str
) -> None:
    """Shared chat pipeline: moderation → quota → context+role → AI → reply.
    Used by both typed text (on_text) and transcribed voice (on_voice)."""
    mod = await moderate(text)
    if not mod.allowed:
        await message.answer(_("mod.blocked"))
        return

    # An active uploaded document turns the chat into doc Q&A (admin-priced cost).
    document = await get_document(user.user_id) if user.is_premium else None
    doc_cost = await pricing.document_cost(session) if document else None

    try:
        qstate = await consume_text(
            session, user, user.selected_model, cost=doc_cost if document else None
        )
    except QuotaExceeded as exc:
        key = "quota.exceeded.premium" if exc.state.is_premium else "quota.exceeded.free"
        await message.answer(
            _(key, used=exc.state.used, limit=exc.state.limit),
            reply_markup=account_keyboard(_),
        )
        return

    # FIX: #2 - wrap get_context in try/except so a Redis failure between charge
    # and context-read doesn't crash with no refund (was: unguarded Redis read).
    try:
        history = await get_context(user.user_id) if user.context_enabled else None
    except Exception:  # noqa: BLE001 — Redis down: fallback without context
        history = None
    system = user.custom_role if (user.role_enabled and user.custom_role) else None

    prompt = text
    if document:
        prompt = (
            f"Документ «{document['name']}»:\n\n{document['text']}\n\n"
            f"Вопрос: {text}"
        )

    chat_cfg = await pricing.chat_config(session)
    voice_on = await feature_flags.is_enabled(session, "voice_output")

    # Streaming (ТЗ §3): edit the reply progressively when enabled. Not used for
    # document Q&A. Falls back to the buffered path if no provider can stream.
    if chat_cfg.get("streaming_enabled") and not document:
        started, ok, full, interrupted = await _stream_reply(
            message, _, model_key=user.selected_model, prompt=prompt,
            system=system, history=history, locale=user.language_code,
            markdown=chat_cfg["markdown_enabled"], voice=voice_on,
        )
        if started:
            if not ok:
                from core.services.quota import effective_text_cost

                await refund_text(
                    session, user,
                    await effective_text_cost(session, user.selected_model),
                    credits_charged=qstate.credits_charged,
                    was_premium=qstate.is_premium,  # FIX: B9
                )
                await message.answer(_("ai.unavailable"))
                return
            # FIX: SKILL-AI3 - use the explicit `interrupted` flag instead of the
            # `len(full) < 30` heuristic. The flag is set by _stream_reply when the
            # async-for loop exits via an exception (mid-stream failure), so a valid
            # short reply ("Yes.", "OK.") no longer triggers a false-positive refund.
            if interrupted:
                from core.services.quota import effective_text_cost
                # Show the partial text so the user isn't left with nothing, THEN
                # refund — the partial was free.
                if full:
                    await message.answer(full, parse_mode=None)
                await refund_text(
                    session, user,
                    await effective_text_cost(session, user.selected_model),
                    credits_charged=qstate.credits_charged,
                    was_premium=qstate.is_premium,
                )
                await message.answer(_("ai.unavailable"))
                return
            if user.context_enabled:
                await append_context(
                    user.user_id, text, full, max_pairs=chat_cfg["memory_pairs"]
                )
            await _maybe_ad(message, session, user, _)
            return
        # nothing streamed → fall through to the buffered request below

    await message.bot.send_chat_action(message.chat.id, "typing")
    # FIX: AUDIT-12 - wrap ai_chat in try/except so provider raise triggers refund
    try:
        result = await ai_chat(
            user.selected_model, prompt, system=system, history=history,
            locale=user.language_code,
        )
    except Exception:
        from core.services.quota import effective_text_cost
        await refund_text(
            session, user,
            doc_cost if document else await effective_text_cost(session, user.selected_model),
            credits_charged=qstate.credits_charged,
            was_premium=qstate.is_premium,
        )
        await message.answer(_("ai.unavailable"))
        return

    # Provider down / rate-limited → return the consumed quota and stop (don't
    # store a non-answer in context).
    if not result.ok:
        from core.services.quota import effective_text_cost

        await refund_text(
            session, user,
            doc_cost if document else await effective_text_cost(session, user.selected_model),
            credits_charged=qstate.credits_charged,
            was_premium=qstate.is_premium,  # FIX: B9
        )
        await message.answer(result.text or _("ai.unavailable"), parse_mode=None)
        return

    # FIX: AI-13 - empty-result guard. If the provider returned ok=True with an
    # empty text (Anthropic safety block, OpenAI null content), refund and surface
    # an error — don't store an empty reply in context or charge the user.
    if not (result.text or "").strip():
        from core.services.quota import effective_text_cost
        await refund_text(
            session, user,
            doc_cost if document else await effective_text_cost(session, user.selected_model),
            credits_charged=qstate.credits_charged,
            was_premium=qstate.is_premium,
        )
        await message.answer(_("ai.unavailable"), parse_mode=None)
        return

    if user.context_enabled:
        await append_context(
            user.user_id, text, result.text, max_pairs=chat_cfg["memory_pairs"]
        )

    # Render as safe Telegram HTML when markdown is enabled (escapes stray markup);
    # _send_reply falls back to plain text if Telegram still rejects it.
    await _send_reply(
        message, result.text, markdown=chat_cfg["markdown_enabled"],
        reply_markup=_reply_actions(_, voice=voice_on),
    )
    await _maybe_ad(message, session, user, _)


# Private-chat only: in groups the catch-all must NOT fire on every message —
# group mentions/replies are owned by bot.handlers.groups (registered earlier).
@router.message(F.chat.type == "private", F.text & ~F.text.startswith("/"))
async def on_text(
    message: Message, session: AsyncSession, user: User, _: Translator
) -> None:
    if user.is_banned:
        await message.answer(_("common.banned"))
        return
    await _answer_text(message, session, user, _, message.text)


@router.message(F.chat.type == "private", F.photo)
async def on_photo(
    message: Message, state: FSMContext, session: AsyncSession, user: User, _: Translator
) -> None:
    """A bare photo in PRIVATE chat. With a caption AND photo-edit enabled, ask whether
    to describe (vision §30) or edit it (img2img §3). Otherwise → vision describe.
    Gated to private like on_text: in groups the bot must not react to every photo."""
    if user.is_banned:
        await message.answer(_("common.banned"))
        return
    caption = (message.caption or "").strip()
    edit_on = await feature_flags.is_enabled(session, "photo_edit")
    if caption and edit_on:
        # Stash the photo + instruction so the choice callbacks can act on them
        # (file_id is too long for callback_data).
        await state.update_data(pe_file=message.photo[-1].file_id, pe_prompt=caption)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=_("photo.btn_describe"), callback_data="photoact:describe"),
            InlineKeyboardButton(text=_("photo.btn_edit"), callback_data="photoact:edit"),
        ]])
        await message.answer(_("photo.choose"), reply_markup=kb)
        return
    await _do_vision(message, session, user, _, message.photo[-1].file_id, caption or None)


async def _do_vision(
    message: Message, session: AsyncSession, user: User, _: Translator,
    file_id: str, caption: str | None,
) -> None:
    """Vision describe path (§30): charge text quota, describe the image, refund on
    failure."""
    if not await feature_flags.is_enabled(session, "vision"):
        await message.answer(_("vision.coming_soon"))
        return
    # Moderate the user-supplied caption before it reaches the AI — every other
    # prompt entry point (chat/search/photo/video/music) moderates; this one didn't.
    if caption and not (await moderate(caption)).allowed:
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
    await message.bot.send_chat_action(message.chat.id, "typing")
    # FIX: F1 - download the file INSIDE the try/except so a download failure (file_id
    # expired, network, Telegram API) triggers the refund path. Previously the download
    # sat OUTSIDE the try and a failure left the user charged with no refund.
    try:
        buf = await message.bot.download(file_id)
        result = await describe_image(
            buf.read(), prompt=caption, locale=user.language_code
        )
    except ProviderUnavailable:
        # vision unavailable → return the charge (to ✨ if that's what paid)
        await refund_text(session, user, credits_charged=qstate.credits_charged,
                          was_premium=qstate.is_premium)  # FIX: C7
        await message.answer(_("vision.coming_soon"))
        return
    except Exception:  # noqa: BLE001
        await refund_text(session, user, credits_charged=qstate.credits_charged,
                          was_premium=qstate.is_premium)  # failed → refund  # FIX: B9
        await message.answer(_("vision.failed"))
        return
    for part in _split_text(result.text):
        await message.answer(part, parse_mode=None)


@router.callback_query(F.data == "photoact:describe")
async def cb_photo_describe(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
    user: User, _: Translator,
) -> None:
    data = await state.get_data()
    file_id = data.get("pe_file")
    if not file_id:
        await callback.answer()
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await _do_vision(callback.message, session, user, _, file_id, data.get("pe_prompt"))


@router.callback_query(F.data == "photoact:edit")
async def cb_photo_edit(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
    user: User, _: Translator,
) -> None:
    """Edit the stashed photo per its caption via img2img (ТЗ §3)."""
    data = await state.get_data()
    file_id = data.get("pe_file")
    prompt = (data.get("pe_prompt") or "").strip()
    if not file_id:
        await callback.answer()
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    if not prompt:
        await callback.message.answer(_("photo.edit_no_caption"))
        return
    if not await packs.try_consume(session, user.user_id, "image", PHOTO_EDIT_COST):
        from bot.keyboards.photo_config import topup_image_kb
        await callback.message.answer(_("gate.pack_empty"), reply_markup=topup_image_kb(_))
        return
    # FIX: F2 - moderate the user-supplied caption BEFORE generating, mirroring every
    # other free-text→AI entry point (chat/search/photo/video/music/documents/inline).
    # Without this, cb_photo_edit was the only unmoderated path to generate_image.
    if not (await moderate(prompt)).allowed:
        await packs.refund(session, user.user_id, "image", PHOTO_EDIT_COST)
        await callback.message.answer(_("mod.blocked"))
        return
    await callback.message.bot.send_chat_action(callback.message.chat.id, "upload_photo")
    note = await callback.message.answer(_("photo.edit_working"))
    try:
        buf = await callback.message.bot.download(file_id)
        ref = await storage.save_upload(buf.read(), "png", prefix="uploads")
        results = await generate_image(
            PHOTO_EDIT_SERVICE, prompt, {"count": 1, "image_refs": [ref]}
        )
    except ProviderUnavailable:
        await packs.refund(session, user.user_id, "image", PHOTO_EDIT_COST)
        await note.edit_text(_("photo.edit_unavailable"))
        return
    except Exception:  # noqa: BLE001
        await packs.refund(session, user.user_id, "image", PHOTO_EDIT_COST)
        await note.edit_text(_("photo.edit_failed"))
        return
    if not results:
        await packs.refund(session, user.user_id, "image", PHOTO_EDIT_COST)
        await note.edit_text(_("photo.edit_failed"))
        return
    img = results[0]
    photo = img.url or BufferedInputFile(img.data, "edited.png")
    await callback.message.answer_photo(photo, caption=_("photo.edit_done"))
    with contextlib.suppress(Exception):
        await note.delete()


@router.message(F.chat.type == "private", F.voice)
async def on_voice(message: Message, session: AsyncSession, user: User, _: Translator) -> None:
    """Voice input (§30): transcribe the voice note, echo what was heard, then run
    it through the same chat pipeline as typed text. Admin-controlled from the panel:
    the `voice_input` master switch turns the whole feature on/off, and
    `voice_input_free` decides the audience (Premium-only by default, or everyone).
    Gated to private like on_text: in groups the bot must not react to every voice note."""
    if user.is_banned:
        await message.answer(_("common.banned"))
        return
    # Master on/off (default ON). The flag defaults to True and get_flags() merges over
    # that default, so a fresh DB keeps voice enabled — while the admin can still turn
    # the whole feature off from the panel (the toggle is wired, not cosmetic).
    if not await feature_flags.is_enabled(session, "voice_input"):
        await message.answer(_("voice_in.coming_soon"))
        return
    # Audience gate: Premium-only unless the admin opened voice input to free users
    # (`voice_input_free`). This is the free/paid control surfaced in the admin panel.
    if not user.is_premium and not await feature_flags.is_enabled(session, "voice_input_free"):
        await message.answer(_("gate.premium_voice"))
        return

    from core.ai_router.stt_adapter import stt

    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        buf = await message.bot.download(message.voice.file_id)
        text = await stt().transcribe(buf.read(), locale=user.language_code)
    except ProviderUnavailable:
        await message.answer(_("voice_in.coming_soon"))  # STT not configured
        return
    except Exception:  # noqa: BLE001
        await message.answer(_("voice_in.failed"))
        return

    if not text:
        await message.answer(_("voice_in.empty"))
        return

    # Show what we understood (so a misheard query is obvious), then answer it.
    await message.answer(_("voice_in.heard", text=text), parse_mode=None)
    await _answer_text(message, session, user, _, text)


@router.callback_query(F.data == "msg:translate")
async def cb_translate(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    if user.is_banned:
        await callback.answer(_("common.banned"), show_alert=True)
        return
    # Guard a rapid double-tap of the 🌐 button from double-charging the text quota:
    # claim a short per-message lock; a second tap within the window is acknowledged
    # but not re-run (a deliberate re-translate later, after the TTL, still works).
    from core.redis_client import first_seen
    lock = f"tr:{callback.message.chat.id}:{callback.message.message_id}"
    if not await first_seen(lock, 15):
        await callback.answer()
        return
    # Use the full stashed reply when this was a chunked, multi-message answer (the
    # button sits on the last chunk); otherwise the visible message text.
    source = await get_full_reply(callback.message.chat.id, callback.message.message_id)
    source = source or (callback.message.text or "")
    # Translation is a generation too — charge the text quota (Gate#1).
    try:
        qstate = await consume_text(session, user, user.selected_model)
    except QuotaExceeded as exc:
        key = "quota.exceeded.premium" if exc.state.is_premium else "quota.exceeded.free"
        await callback.answer(
            _(key, used=exc.state.used, limit=exc.state.limit), show_alert=True
        )
        return
    target = user.language_code or "ru"
    # FIX: AI-1 - import effective_text_cost ONCE at the top of the try block so the
    # except branch can refund without a NameError (was: import was at line 553 inside
    # the unreachable `if not result.ok:` block, so any provider exception left the
    # user charged with no refund and crashed the handler with NameError).
    from core.services.quota import effective_text_cost
    # FIX: AUDIT-12 - wrap translate ai_chat in try/except
    try:
        result = await ai_chat(
            user.selected_model,
            f"Переведи следующий текст на язык пользователя ({target}). "
            f"Верни только перевод:\n\n{source}",
            locale=target,
        )
    except Exception:
        await refund_text(
            session, user, await effective_text_cost(session, user.selected_model),
            credits_charged=qstate.credits_charged, was_premium=qstate.is_premium)
        await callback.message.answer(_("ai.unavailable"))
        return
    if not result.ok:
        # Provider down / rate-limited → refund the quota and surface the error,
        # then STOP (mirrors on_text). The explicit return keeps any future
        # success-only step below from running on a failed translation.
        await refund_text(session, user, await effective_text_cost(session, user.selected_model),
                          credits_charged=qstate.credits_charged,
                          was_premium=qstate.is_premium)  # FIX: B9
        await callback.message.answer(result.text, parse_mode=None)
        await callback.answer()
        return
    chat_cfg = await pricing.chat_config(session)
    await _send_reply(callback.message, result.text, markdown=chat_cfg["markdown_enabled"])
    await callback.answer()


@router.callback_query(F.data == "msg:voice")
async def cb_voice(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    # FIX: AUDIT-112 - Redis lock on voice button (15s) to prevent TTS cost abuse.
    # FIX: AUDIT-P6 - first_seen lives in core.redis_client, NOT core.services.ratelimit
    # (which only defines allow/peek/incr/reset). The wrong import raised ImportError on
    # every tap — outside the try below — so the 🔊 button was 100% dead. cb_translate
    # imports it from the correct module.
    from core.redis_client import first_seen
    lock_key = f"voice:{callback.message.chat.id}:{callback.message.message_id}"
    try:
        if not await first_seen(lock_key, 15):
            await callback.answer()
            return
    except Exception:
        pass  # fail-open on Redis down
    # Admin kill-switch (also covers stale buttons on old messages).
    if not await feature_flags.is_enabled(session, "voice_output"):
        await callback.answer(_("tts.unavailable"), show_alert=True)
        return
    if not user.is_premium:
        await callback.answer(_("gate.premium"), show_alert=True)
        return
    # Voice the full stashed reply for a chunked answer; else the visible message.
    text = await get_full_reply(callback.message.chat.id, callback.message.message_id)
    text = text or (callback.message.text or "")
    if not text:
        await callback.answer()
        return
    await callback.answer()
    try:
        audio = await tts().speak(text, voice=user.voice_name)
    except ProviderUnavailable:
        await callback.message.answer(_("tts.unavailable"))
        return
    except Exception:  # noqa: BLE001
        await callback.message.answer(_("tts.failed"))
        return
    from aiogram.types import BufferedInputFile

    await callback.message.answer_voice(
        BufferedInputFile(audio, filename="voice.ogg")
    )


@router.callback_query(F.data.in_({"fb:up", "fb:down"}))
async def cb_feedback(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    """👍/👎 on an AI reply (§7): record the rating + a snippet of the rated text."""
    rating = "up" if callback.data == "fb:up" else "down"
    snippet = callback.message.text if callback.message else None
    await feedback.record_rating(session, user.user_id, rating, snippet)
    await callback.answer(_("fb.thanks"))


@router.message(Command("report"))
async def on_report(
    message: Message, command: CommandObject, session: AsyncSession, user: User, _: Translator
) -> None:
    """/report <text> — file a complaint (§7)."""
    if user.is_banned:
        await message.answer(_("common.banned"))
        return
    text = (command.args or "").strip()
    if not text:
        await message.answer(_("report.usage"))
        return
    await feedback.record_complaint(session, user.user_id, text)
    await message.answer(_("report.thanks"))
