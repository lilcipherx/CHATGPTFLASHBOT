"""/video service sub-menus + async generation (§21A).

The 6 config services (Seedance, Veo, Grok, Kling AI, Hailuo, Pika) open a config
sub-menu; sending a prompt deducts video credits, creates a generation_job and
enqueues the ARQ worker, which submits/polls the provider and delivers the
result (refunding on failure). Kling Effects/Motion live in handlers/kling.py."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.menus import video_menu
from bot.keyboards.video_config import topup_video_kb, video_config_kb
from bot.states import VideoSG
from core.ai_router.video_adapters import provider_for
from core.ai_router.video_specs import VIDEO_SPECS
from core.i18n import Translator
from core.models import GenerationJob, User
from core.queue import QueueUnavailable, enqueue_or_refund
from core.services import packs, pricing
from core.services.moderation import moderate

router = Router()


@router.callback_query(F.data == "video:back")
async def cb_video_back(callback: CallbackQuery, state: FSMContext, _: Translator) -> None:
    await state.set_state(VideoSG.menu)
    await callback.message.edit_text(_("video.menu"), reply_markup=video_menu(_))
    await callback.answer()


@router.callback_query(F.data.startswith("video:"))
async def cb_video_service(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, _: Translator
) -> None:
    service = callback.data.split(":", 1)[1]
    spec = VIDEO_SPECS.get(service)
    if spec is None:
        # Видеоэффекты bridges to the Mini App; kling_* handled in handlers/kling.py
        if service == "videoeffects":
            from bot.keyboards.inline import open_app_markup

            await callback.message.answer(_("video.effects_hint"), reply_markup=open_app_markup(_))
            await callback.answer()
        else:
            await callback.answer(_("common.coming_soon"), show_alert=True)
        return
    cfg = dict(spec.default)
    await state.set_state(VideoSG.service_config)
    await state.update_data(service=service, cfg=cfg, awaiting_seed=False)
    dl = await pricing.doc_links(session)
    so = (await pricing.service_options(session)).get(spec.key)
    await callback.message.edit_text(
        _(f"spec.desc.{spec.key}"), reply_markup=video_config_kb(_, spec, cfg, dl, so)
    )
    await callback.answer()


@router.callback_query(VideoSG.service_config, F.data.startswith("vcfg:"))
async def cb_video_config(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, _: Translator
) -> None:
    # FIX: B13 - wrap callback_data parse in try/except so a forged/malformed
    # payload (vcfg:foo / vcfg:duration:abc) doesn't crash the handler.
    try:
        _p, field, value = callback.data.split(":", 2)
    except ValueError:
        await callback.answer()
        return
    data = await state.get_data()
    spec = VIDEO_SPECS[data["service"]]
    cfg = data["cfg"]

    if field == "seed" and value == "ask":
        await state.update_data(awaiting_seed=True)
        await callback.message.answer(_("seed.ask"))
        await callback.answer()
        return
    before = cfg.get(field)
    if value == "toggle":
        cfg[field] = not cfg.get(field, False)
    elif field == "duration":
        try:
            cfg[field] = int(value)
        except ValueError:
            await callback.answer()
            return
    else:
        cfg[field] = value

    await state.update_data(cfg=cfg)
    # Re-tapping the already-selected option leaves the keyboard identical; only
    # edit when something changed so Telegram doesn't raise "message is not modified".
    if cfg.get(field) != before:
        dl = await pricing.doc_links(session)
        so = (await pricing.service_options(session)).get(spec.key)
        await callback.message.edit_reply_markup(
            reply_markup=video_config_kb(_, spec, cfg, dl, so)
        )
    await callback.answer()


@router.message(VideoSG.service_config, F.photo)
async def on_video_image(message: Message, state: FSMContext, _: Translator) -> None:
    """Image-to-video services accept a photo as the first frame / base (§21A)."""
    data = await state.get_data()
    spec = VIDEO_SPECS.get(data.get("service", ""))
    if spec is None or not spec.image_input:
        return
    cfg = data["cfg"]
    cfg["image_file_id"] = message.photo[-1].file_id
    await state.update_data(cfg=cfg)
    await message.answer(_("video.image_saved"))


@router.message(VideoSG.service_config, F.text & ~F.text.startswith("/"))
async def on_video_prompt(
    message: Message, state: FSMContext, session: AsyncSession, user: User, _: Translator
) -> None:
    data = await state.get_data()
    service = data["service"]
    spec = VIDEO_SPECS[service]
    cfg = data["cfg"]

    if data.get("awaiting_seed"):
        # FIX: F23 - port R9 hardening from photo.py: parse with bounds (0 <= seed
        # <= 2**31-1, the common provider int32 limit) so a malformed/huge value
        # doesn't reach the provider as a string and 500 there. A non-digit falls
        # through to "treat as prompt" (existing behaviour).
        seed_text = message.text.strip()
        try:
            seed_val = int(seed_text)
            if not (0 <= seed_val <= 2_147_483_647):
                raise ValueError("out of range")
        except ValueError:
            await state.update_data(awaiting_seed=False)
        else:
            cfg["seed"] = str(seed_val)
            await state.update_data(cfg=cfg, awaiting_seed=False)
            dl = await pricing.doc_links(session)
            so = (await pricing.service_options(session)).get(spec.key)
            await message.answer(
                _("seed.saved"), reply_markup=video_config_kb(_, spec, cfg, dl, so)
            )
            return

    if not (await moderate(message.text)).allowed:
        await message.answer(_("mod.blocked"))
        return

    provider = provider_for(service)
    if provider is None or not provider.is_available():
        await message.answer(_("gen.unavailable"))
        return

    cost = spec.cost(cfg)
    pack = spec.pack  # "video" for most, "image" for Midjourney Video (§26C)
    # Charge with commit=False and commit it together with the job below so a hard
    # crash between the two can't burn a credit with no job (the deduction holds its
    # row lock until that single commit — no slow I/O in between).
    if not await packs.try_consume(session, user.user_id, pack, cost, commit=False):
        await session.rollback()
        from bot.keyboards.photo_config import topup_image_kb
        kb = topup_image_kb(_) if pack == "image" else topup_video_kb(_)
        await message.answer(_("gate.pack_empty"), reply_markup=kb)
        return

    job = GenerationJob(
        user_id=user.user_id,
        service=service,
        model_variant=str(cfg.get("model") or cfg.get("mode") or ""),
        params={**cfg, "prompt": message.text},
        cost_credits=cost,
        pack_type=pack,
        status="pending",
    )
    session.add(job)
    await session.commit()  # charge + job atomic
    try:
        await enqueue_or_refund(session, job, "process_video_job")
    except QueueUnavailable:
        await message.answer(_("gen.error_refund"))
        return

    await message.answer(
        _("gen.video_started")
    )
