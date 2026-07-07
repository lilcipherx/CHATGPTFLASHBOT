"""Music generation (§8): Suno V5.5 / Lyria 3 Pro.

Both are paywalled — a music pack is required (no free trial). With credits, the
user picks a service, sends a prompt, and an async job is created (1 credit),
delivered as audio by the music worker."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states.states import MusicSG
from core.ai_router.music_adapters import provider_for
from core.i18n import Translator
from core.models import GenerationJob, User
from core.queue import QueueUnavailable, enqueue_or_refund
from core.services import packs
from core.services.moderation import moderate

router = Router()

MUSIC_COST = 1  # 1 credit = 1 song (Q9 default)

# FIX: AUDIT-M13 - single source of truth for the Suno model, so the label shown to
# the (paying) user matches the model actually sent to the API. The previous "Suno
# V5.5" label was cosmetic — the adapter always sent suno-v4 — so the user was
# misled. Bump SUNO_MODEL (and the label) together if a newer verified model id lands.
SUNO_MODEL = "suno-v4"


def _topup_kb(_: Translator) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("btn.topup"), callback_data="pack:music_pack")]
        ]
    )


@router.callback_query(F.data.startswith("music:"))
async def cb_music_service(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, _: Translator
) -> None:
    service = callback.data.split(":", 1)[1]  # suno | lyria
    if await packs.get_balance(session, user.user_id, "music") < MUSIC_COST:
        await callback.message.answer(_("music.paywall"), reply_markup=_topup_kb(_))
        await callback.answer()
        return
    await state.set_state(MusicSG.awaiting_prompt)
    await state.update_data(service=service)
    name = "Suno" if service == "suno" else "Lyria 3 Pro"
    await callback.message.answer(_("music.prompt", name=name))
    await callback.answer()


@router.message(MusicSG.awaiting_prompt, F.text & ~F.text.startswith("/"))
async def on_music_prompt(
    message: Message, state: FSMContext, session: AsyncSession, user: User, _: Translator
) -> None:
    data = await state.get_data()
    service = data["service"]

    if not (await moderate(message.text)).allowed:
        await message.answer(_("mod.blocked"))
        return

    provider = provider_for(service)
    if provider is None or not provider.is_available():
        await message.answer(_("gen.unavailable"))
        return

    # Charge with commit=False and commit it together with the job below, so a hard
    # crash between the two can't burn a music credit with no job. The deduction
    # holds its row lock until that single commit (no slow I/O in between).
    if not await packs.try_consume(session, user.user_id, "music", MUSIC_COST, commit=False):
        await session.rollback()
        await message.answer(_("music.paywall"), reply_markup=_topup_kb(_))
        return

    job = GenerationJob(
        user_id=user.user_id,
        service=service,
        params={"prompt": message.text, **({"model": SUNO_MODEL} if service == "suno" else {})},
        cost_credits=MUSIC_COST,
        pack_type="music",
        status="pending",
    )
    session.add(job)
    await session.commit()  # charge + job atomic
    await state.clear()
    try:
        await enqueue_or_refund(session, job, "process_music_job")
    except QueueUnavailable:
        await message.answer(_("gen.error_refund"))
        return
    await message.answer(_("gen.music_started"))
