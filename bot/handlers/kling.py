"""Kling Effects (74 templates, 7 pages) + Kling Motion (13 templates) (§21A).

Browse paginated catalog → select template → upload a photo → the photo + chosen
template become an async video job (1 video credit). Catalogs are seeded by
scripts/seed_catalogs.py."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.video_config import topup_video_kb
from bot.states import KlingSG
from core.ai_router.video_adapters import provider_for
from core.i18n import Translator
from core.models import GenerationJob, KlingEffectTemplate, KlingMotionTemplate, User
from core.queue import QueueUnavailable, enqueue_or_refund
from core.services import packs

router = Router()

EFFECT_COST = 1  # video credits per template generation


async def _effects_page(
    session: AsyncSession, page: int, _: Translator
) -> tuple[str, InlineKeyboardMarkup]:
    total_pages = (
        await session.scalar(select(func.max(KlingEffectTemplate.page)))
    ) or 1
    page = max(1, min(page, total_pages))
    rows = (
        await session.scalars(
            select(KlingEffectTemplate)
            .where(KlingEffectTemplate.page == page)
            .order_by(KlingEffectTemplate.position)
        )
    ).all()

    b = InlineKeyboardBuilder()
    for tpl in rows:
        title = ("🆕 " if tpl.is_new else "") + tpl.localized_name(_.locale)
        b.button(text=title, callback_data=f"keff:sel:{tpl.template_id}")
    b.adjust(2)
    nav = InlineKeyboardBuilder()
    nav.button(text="◄", callback_data=f"keff:page:{page - 1}")
    nav.button(text=f"{page}/{total_pages}", callback_data="noop")
    nav.button(text="►", callback_data=f"keff:page:{page + 1}")
    nav.adjust(3)
    b.attach(nav)
    b.row(InlineKeyboardButton(text=_("btn.back"), callback_data="video:back"))
    return _("kling.effects_intro"), b.as_markup()


@router.callback_query(F.data == "video:kling_effects")
async def cb_kling_effects(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, _: Translator
) -> None:
    await state.set_state(KlingSG.browse)
    text, kb = await _effects_page(session, 1, _)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("keff:page:"))
async def cb_kling_effects_page(
    callback: CallbackQuery, session: AsyncSession, _: Translator
) -> None:
    from aiogram.exceptions import TelegramBadRequest

    # FIX: F24 - wrap int() in try/except so a forged/malformed callback_data
    # (keff:page:abc) doesn't crash the handler with ValueError. Mirror contests.py:55-59.
    try:
        page = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    text, kb = await _effects_page(session, page, _)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass  # edge page (already showing first/last) — nothing changed
    await callback.answer()


@router.callback_query(F.data.startswith("keff:sel:"))
async def cb_kling_effect_select(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, _: Translator
) -> None:
    # FIX: F24 - wrap int() in try/except (mirror contests.py:55-59).
    try:
        tpl_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    tpl = await session.get(KlingEffectTemplate, tpl_id)
    if tpl is None:
        await callback.answer()
        return
    name = tpl.localized_name(_.locale)
    await state.set_state(KlingSG.awaiting_photo)
    await state.update_data(kind="kling_effects", template_id=tpl_id, template_name=name)
    await callback.message.answer(_("kling.effect_selected", name=name))
    await callback.answer()


# ----- Kling Motion (13 templates, single page) -----
@router.callback_query(F.data == "video:kling_motion")
async def cb_kling_motion(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, _: Translator
) -> None:
    rows = (
        await session.scalars(
            select(KlingMotionTemplate).order_by(KlingMotionTemplate.position)
        )
    ).all()
    b = InlineKeyboardBuilder()
    for tpl in rows:
        b.button(text=tpl.localized_name(_.locale), callback_data=f"kmot:sel:{tpl.template_id}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text=_("btn.back"), callback_data="video:back"))
    await state.set_state(KlingSG.browse)
    await callback.message.edit_text(_("kling.motion_intro"), reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("kmot:sel:"))
async def cb_kling_motion_select(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, _: Translator
) -> None:
    # FIX: F24 - wrap int() in try/except (mirror contests.py:55-59).
    try:
        tpl_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    tpl = await session.get(KlingMotionTemplate, tpl_id)
    if tpl is None:
        await callback.answer()
        return
    name = tpl.localized_name(_.locale)
    await state.set_state(KlingSG.awaiting_photo)
    await state.update_data(kind="kling_motion", template_id=tpl_id, template_name=name)
    await callback.message.answer(_("kling.motion_selected", name=name))
    await callback.answer()


# ----- photo upload -> async job -----
@router.message(KlingSG.awaiting_photo, F.photo)
async def on_kling_photo(
    message: Message, state: FSMContext, session: AsyncSession, user: User, _: Translator
) -> None:
    data = await state.get_data()
    service = data["kind"]

    provider = provider_for(service)
    if provider is None or not provider.is_available():
        await message.answer(_("gen.unavailable"))
        return

    # Charge with commit=False and commit it together with the job below so a hard
    # crash between the two can't burn a video credit with no job (the deduction
    # holds its row lock until that single commit — no slow I/O in between).
    if not await packs.try_consume(session, user.user_id, "video", EFFECT_COST, commit=False):
        await session.rollback()
        await message.answer(_("gate.pack_empty"), reply_markup=topup_video_kb(_))
        return

    file_id = message.photo[-1].file_id
    job = GenerationJob(
        user_id=user.user_id,
        service=service,
        model_variant=str(data["template_id"]),
        # FIX: AI-8 - use `image_file_id` (not `photo_file_id`) so the video worker
        # (workers/video_tasks.py:138) picks it up and uploads it to S3 before
        # passing the URL to Kling's image2video endpoint. The old name left every
        # Kling Effect/Motion job with no image input → silent text2video fallback.
        params={"template_id": data["template_id"], "image_file_id": file_id},
        cost_credits=EFFECT_COST,
        pack_type="video",
        status="pending",
    )
    session.add(job)
    await session.commit()  # charge + job atomic
    await state.clear()
    try:
        await enqueue_or_refund(session, job, "process_video_job")
    except QueueUnavailable:
        await message.answer(_("gen.error_refund"))
        return
    await message.answer(_("gen.photo_started", name=data["template_name"]))


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()
