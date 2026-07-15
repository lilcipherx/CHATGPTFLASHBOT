"""/photo service sub-menus + image generation (§21B).

Prompt-driven services (GPT Image 2, Nano Banana, Seedream, Midjourney, FLUX 2)
open a config sub-menu (model/quality/ratio/seed) held in FSM data; the user then
sends a prompt to generate. Budget is the weekly quota for GPT Image 2 / Nano
Banana 2 (§10.2) and the image pack otherwise, with atomic deduct + refund on
provider failure."""
from __future__ import annotations

import contextlib  # FIX: F1 - needed for contextlib.suppress in _run_photo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.menus import photo_menu
from bot.keyboards.photo_config import service_config_kb, topup_image_kb
from bot.states import AvatarSG, FaceSwapSG, PhotoSG, UpscaleSG
from core.ai_router.base import ProviderUnavailable
from core.ai_router.image_adapters import generate_image
from core.ai_router.image_specs import PHOTO_SPECS
from core.i18n import Translator
from core.models import GenerationJob, User
from core.queue import QueueUnavailable, enqueue, enqueue_or_refund
from core.services import feature_flags, packs, pricing, promos
from core.services.moderation import moderate
from core.services.quota import QuotaExceeded, consume_text, refund_text

router = Router()

FACESWAP_COST = 1          # §22A — Face Swap = 1 image credit (fallback default)
UPSCALE_COST = {"x2": 2, "x4": 4}  # §22A — Upscale X2=2, X4=4 (fallback defaults)


async def _faceswap_cost(session: AsyncSession) -> int:
    """Live-цена Face Swap из админ-конфига (блок phototools), с откатом на дефолт."""
    block = (await pricing.get_config(session)).get("phototools", {})
    try:
        return max(0, int(block.get("face_swap", FACESWAP_COST)))
    except (TypeError, ValueError):
        return FACESWAP_COST


async def _upscale_cost(session: AsyncSession, factor: str) -> int:
    """Live-цена апскейла X2/X4 из админ-конфига, с откатом на дефолт тарифа."""
    block = (await pricing.get_config(session)).get("phototools", {})
    fallback = UPSCALE_COST.get(factor, 2)
    try:
        return max(0, int(block.get(f"upscale_{factor}", fallback)))
    except (TypeError, ValueError):
        return fallback


def _upscale_kb(_: Translator) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=_("upscale.x2"), callback_data="upscale:x2"),
        InlineKeyboardButton(text=_("upscale.x4"), callback_data="upscale:x4"),
    ]])


async def _open_service(
    message: Message, state: FSMContext, service: str, session: AsyncSession, _: Translator
) -> None:
    spec = PHOTO_SPECS[service]
    cfg = dict(spec.default)
    await state.set_state(PhotoSG.service_config)
    await state.update_data(service=service, cfg=cfg, awaiting_seed=False)
    dl = await pricing.doc_links(session)
    so = (await pricing.service_options(session)).get(spec.key)
    await message.answer(
        _(f"spec.desc.{spec.key}"), reply_markup=service_config_kb(_, spec, cfg, dl, so)
    )


# ----- hidden shortcuts (§25A): /wow -> GPT Image 2, /Midjourney -> direct MJ -----
@router.message(Command("wow"))
async def cmd_wow(
    message: Message, state: FSMContext, session: AsyncSession, _: Translator
) -> None:
    await _open_service(message, state, "gpt_image2", session, _)


@router.message(Command("Midjourney", "midjourney", ignore_case=True))
async def cmd_midjourney(
    message: Message, state: FSMContext, session: AsyncSession, _: Translator
) -> None:
    await _open_service(message, state, "midjourney", session, _)


async def _avatar_price(session: AsyncSession, user: User) -> int:
    """Avatar Stars price for ``user``, discounted by max(sale, applied promo code)."""
    base = await pricing.avatar_price(session, apply_sale=False)
    return pricing.discount(base, await promos.checkout_percent(session, user))


# ----- Avatar pack (§15A.1): /ava | /avatar, 200⭐ one-time, async ~15 min -----
@router.message(Command("ava", "avatar"))
async def cmd_ava(
    message: Message, session: AsyncSession, user: User, _: Translator
) -> None:
    if not await feature_flags.is_enabled(session, "avatar"):
        await message.answer(_("common.coming_soon"))
        return
    price = await _avatar_price(session, user)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=_("avatar.buy_btn", price=price), callback_data="avatar:buy"
            )]
        ]
    )
    await message.answer(_("avatar.info", price=price), reply_markup=kb)


@router.callback_query(F.data == "avatar:buy")
async def cb_avatar_buy(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    if not await feature_flags.is_enabled(session, "avatar"):
        await callback.answer(_("common.coming_soon"), show_alert=True)
        return
    title = _("avatar.title")
    price = await _avatar_price(session, user)
    # Abandoned-cart tracking (ТЗ §7): «resume» re-opens the avatar buy prompt.
    from core.services import checkout
    await checkout.record_intent(
        session, user.user_id, kind="avatar", resume_cb="avatar:buy",
        gateway="stars", amount=price,
    )
    await callback.message.answer_invoice(
        title=title,
        description=_("avatar.invoice_desc"),
        payload="avatar",
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=price)],
    )
    await callback.answer()


def _budget(spec, cfg: dict) -> str:
    """'image' pack or 'weekly'. Nano Banana Pro switches NB to the image pack."""
    if spec.key == "nano_banana" and cfg.get("model") == "nbpro":
        return "image"
    return "image" if spec.pack == "image" else "weekly"


@router.callback_query(F.data == "photo:back")
async def cb_photo_back(callback: CallbackQuery, state: FSMContext, _: Translator) -> None:
    await state.set_state(PhotoSG.menu)
    await callback.message.edit_text(_("photo.menu"), reply_markup=photo_menu(_))
    await callback.answer()


@router.callback_query(F.data.startswith("photo:"))
async def cb_photo_service(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
    user: User, _: Translator,
) -> None:
    service = callback.data.split(":", 1)[1]

    # Tools with their own flows (not prompt-config services).
    if service == "avatar":
        if not await feature_flags.is_enabled(session, "avatar"):
            await callback.answer(_("common.coming_soon"), show_alert=True)
            return
        price = await _avatar_price(session, user)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text=_("avatar.buy_btn", price=price), callback_data="avatar:buy")]])
        await callback.message.answer(_("avatar.info", price=price), reply_markup=kb)
        await callback.answer()
        return
    if service == "faceswap":
        if not await feature_flags.is_enabled(session, "faceswap"):
            await callback.answer(_("common.coming_soon"), show_alert=True)
            return
        await state.set_state(FaceSwapSG.awaiting_target)
        await callback.message.answer(_("faceswap.step1"))
        await callback.answer()
        return
    if service == "upscale":
        if not await feature_flags.is_enabled(session, "upscale"):
            await callback.answer(_("common.coming_soon"), show_alert=True)
            return
        await callback.message.answer(_("upscale.intro"), reply_markup=_upscale_kb(_))
        await callback.answer()
        return

    if service == "recraft" and not await feature_flags.is_enabled(session, "recraft"):
        await callback.answer(_("common.coming_soon"), show_alert=True)
        return

    spec = PHOTO_SPECS.get(service)
    if spec is None:
        # FIX: AUDIT13-L13 - the "Фотоэффекты" menu button (photo:photoeffects) has no
        # spec, so it used to fall to a bare "coming soon" with no path forward. Bridge
        # to the Mini App like the parallel video "videoeffects" entry does.
        if service == "photoeffects":
            from bot.keyboards.inline import open_app_markup

            await callback.message.answer(_("photo.effects_hint"), reply_markup=open_app_markup(_))
            await callback.answer()
        else:
            await callback.answer(_("common.coming_soon"), show_alert=True)
        return

    cfg = dict(spec.default)
    so = (await pricing.service_options(session)).get(spec.key) or {}
    counts = so.get("counts") or spec.counts
    # Default the number of variants from the admin `generation.image_variants`
    # knob (ТЗ §5), bounded by what this service can output. The user can still
    # change it via the count selector below.
    if counts:
        variants = (await pricing.generation(session))["image_variants"]
        cfg["count"] = max(1, min(variants, max(counts)))
    await state.set_state(PhotoSG.service_config)
    await state.update_data(service=service, cfg=cfg)
    dl = await pricing.doc_links(session)
    await callback.message.edit_text(
        _(f"spec.desc.{spec.key}"), reply_markup=service_config_kb(_, spec, cfg, dl, so)
    )
    await callback.answer()


# ----- Face Swap (§15A): 2-step photo upload, 1 image credit -----
@router.message(FaceSwapSG.awaiting_target, F.photo)
async def faceswap_target(message: Message, state: FSMContext, _: Translator) -> None:
    await state.update_data(target=message.photo[-1].file_id)
    await state.set_state(FaceSwapSG.awaiting_source)
    await message.answer(_("faceswap.step2"))


@router.message(FaceSwapSG.awaiting_source, F.photo)
async def faceswap_source(
    message: Message, state: FSMContext, session: AsyncSession, user: User, _: Translator
) -> None:
    data = await state.get_data()
    fs_cost = await _faceswap_cost(session)
    # Charge with commit=False and commit it together with the job below so a hard
    # crash between the two can't burn an image credit with no job.
    if not await packs.try_consume(session, user.user_id, "image", fs_cost, commit=False):
        await session.rollback()
        await state.clear()
        await message.answer(_("gate.pack_empty"), reply_markup=topup_image_kb(_))
        return
    job = GenerationJob(
        user_id=user.user_id, service="faceswap",
        params={"target": data.get("target"), "source": message.photo[-1].file_id},
        cost_credits=fs_cost, pack_type="image", status="pending",
    )
    session.add(job)
    await session.commit()  # charge + job atomic
    await state.clear()
    try:
        await enqueue_or_refund(session, job, "process_faceswap_job")
    except QueueUnavailable:
        await message.answer(_("gen.error_refund"))
        return
    await message.answer(_("gen.image_started"))


# ----- Upscale X2/X4 (§15A) -----
@router.callback_query(F.data.startswith("upscale:"))
async def cb_upscale_factor(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, _: Translator
) -> None:
    factor = callback.data.split(":", 1)[1]
    if factor not in UPSCALE_COST:
        await callback.answer()
        return
    await state.set_state(UpscaleSG.awaiting_image)
    await state.update_data(factor=factor)
    cost = await _upscale_cost(session, factor)
    await callback.message.answer(_("upscale.send_image", cost=cost))
    await callback.answer()


@router.message(UpscaleSG.awaiting_image, F.photo)
async def upscale_image(
    message: Message, state: FSMContext, session: AsyncSession, user: User, _: Translator
) -> None:
    data = await state.get_data()
    factor = data.get("factor", "x2")
    cost = await _upscale_cost(session, factor)
    # Charge with commit=False and commit it together with the job below so a hard
    # crash between the two can't burn an image credit with no job.
    if not await packs.try_consume(session, user.user_id, "image", cost, commit=False):
        await session.rollback()
        await state.clear()
        await message.answer(_("gate.pack_empty"), reply_markup=topup_image_kb(_))
        return
    job = GenerationJob(
        user_id=user.user_id, service="upscale",
        params={"factor": factor, "image": message.photo[-1].file_id},
        cost_credits=cost, pack_type="image", status="pending",
    )
    session.add(job)
    await session.commit()  # charge + job atomic
    await state.clear()
    try:
        await enqueue_or_refund(session, job, "process_upscale_job")
    except QueueUnavailable:
        await message.answer(_("gen.error_refund"))
        return
    await message.answer(_("gen.image_started"))


@router.callback_query(PhotoSG.service_config, F.data.startswith("pcfg:"))
async def cb_photo_config(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, _: Translator
) -> None:
    # FIX: B14 - wrap callback_data parse in try/except (mirror contests.py:55-59).
    try:
        _p, field, value = callback.data.split(":", 2)
    except ValueError:
        await callback.answer()
        return
    data = await state.get_data()
    spec = PHOTO_SPECS[data["service"]]
    cfg = data["cfg"]

    if field == "seed" and value == "ask":
        await state.update_data(awaiting_seed=True)
        await callback.message.answer(_("seed.ask"))
        await callback.answer()
        return

    before = cfg.get(field)
    cfg[field] = value
    await state.update_data(cfg=cfg)
    # Re-tapping the already-selected option leaves the keyboard identical; only
    # edit when something changed so Telegram doesn't raise "message is not modified".
    if cfg.get(field) != before:
        dl = await pricing.doc_links(session)
        so = (await pricing.service_options(session)).get(spec.key)
        await callback.message.edit_reply_markup(
            reply_markup=service_config_kb(_, spec, cfg, dl, so)
        )
    await callback.answer()


@router.message(PhotoSG.service_config, F.text & ~F.text.startswith("/"))
async def on_photo_prompt(
    message: Message, state: FSMContext, session: AsyncSession, user: User, _: Translator
) -> None:
    data = await state.get_data()
    spec = PHOTO_SPECS[data["service"]]
    cfg = data["cfg"]

    # capture a pending seed entry instead of treating it as a prompt
    if data.get("awaiting_seed"):
        # FIX: R9 - harden the seed input: parse with bounds (0 <= seed <= 2**31-1,
        # the common provider limit) so a malformed/huge value doesn't reach the
        # provider as a string and 500 there. A non-digit falls through to "treat as
        # prompt" (existing behaviour) so the user isn't stuck in seed-entry mode.
        seed_text = message.text.strip()
        try:
            seed_val = int(seed_text)
            if not (0 <= seed_val <= 2_147_483_647):
                raise ValueError("out of range")
        except ValueError:
            await state.update_data(awaiting_seed=False)
            # fall through: treat as prompt
        else:
            cfg["seed"] = str(seed_val)
            await state.update_data(cfg=cfg, awaiting_seed=False)
            dl = await pricing.doc_links(session)
            so = (await pricing.service_options(session)).get(spec.key)
            await message.answer(
                _("seed.saved"), reply_markup=service_config_kb(_, spec, cfg, dl, so)
            )
            return

    if not (await moderate(message.text)).allowed:
        await message.answer(_("mod.blocked"))
        return

    await _run_photo(message, state, session, user, spec, cfg, message.text, _)


def _postgen_kb(_: Translator, *, has_file: bool = False) -> InlineKeyboardMarkup:
    """Post-generation actions shown under a freshly generated image (§24A)."""
    rows = [[
        InlineKeyboardButton(text=_("img.more"), callback_data="img:more"),
        InlineKeyboardButton(text=_("img.upscale"), callback_data="img:upscale"),
    ]]
    # Full-quality download (ТЗ §5): re-send the result as an uncompressed file.
    if has_file:
        rows.append([InlineKeyboardButton(text=_("img.file"), callback_data="img:file")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _run_photo(
    message: Message, state: FSMContext, session: AsyncSession, user: User,
    spec, cfg: dict, prompt: str, _: Translator,
) -> None:
    """Charge → generate → deliver with post-gen action buttons. Shared by the
    prompt handler and the «🔄 ещё вариант» regenerate callback.

    Multi-variant (ТЗ §5): the user/admin can request N output images (cfg["count"]
    — set from the config UI's count selector and defaulted from the admin
    `generation.image_variants` knob). Cost scales with the number requested, and
    any variant the provider fails to return is refunded."""
    # Gate BEFORE charging: proceed only when a direct provider is available OR an
    # admin gateway account serves this image model (the pool). Avoids a charge+refund
    # cycle when nothing can serve, and opens gateway-only services from the bot menu.
    from core.ai_router.image_adapters import _IMAGE_PROVIDERS
    from core.services.media_dispatch import has_backend
    if not await has_backend(session, modality="image", model_key=spec.key,
                             direct_provider=_IMAGE_PROVIDERS.get(spec.key)):
        await message.answer(_("gen.unavailable"))
        return

    per = spec.cost(cfg)                              # cost of ONE image
    count = max(1, int(cfg.get("count", 1) or 1))
    cost = per * count                               # charge for all requested
    budget = _budget(spec, cfg)

    qcredits = 0  # ✨ spent on the weekly-quota branch (for a matching refund)
    qwas_premium: bool | None = None  # FIX: B9 - carry is_premium at charge time for refund_text
    if budget == "image":
        if not await packs.try_consume(session, user.user_id, "image", cost):
            await message.answer(_("gate.pack_empty"), reply_markup=topup_image_kb(_))
            return
    else:  # weekly quota (GPT Image 2 / Nano Banana 2), then ✨ balance
        try:
            qstate = await consume_text(session, user, cost=cost)
            qcredits = qstate.credits_charged
            qwas_premium = qstate.is_premium  # FIX: B9
        except QuotaExceeded as exc:
            key = "quota.exceeded.premium" if exc.state.is_premium else "quota.exceeded.free"
            await message.answer(_(key, used=exc.state.used, limit=exc.state.limit))
            return

    wait = await message.answer(_("common.please_wait"))
    try:
        # FIX: AI-14 - pass image_refs to the provider so bot users can do img2img.
        # The bot photo handler doesn't currently capture an uploaded selfie for the
        # standard photo-spec flow (only FaceSwap/Upscale/Avatar have an upload state).
        # When a future state adds `data.get("image_refs")` (list of file_ids or URLs),
        # download+upload each to storage and pass the URLs here. For now, if the
        # caller stashed image_refs in cfg (e.g. via a future upload state), pass them
        # through unchanged so providers that support img2img (OpenAI, Google, BFL)
        # can use them.
        # FIX: OPENROUTER-MEDIA - route through admin-configured image accounts
        # (OpenRouter / Kie / MuAPI…) first, falling back to the direct env adapter.
        # This makes the bot's /photo generation admin-routable exactly like the Mini
        # App effects; behaviour is unchanged when no image account is configured.
        from core.services.media_dispatch import generate_image_routed_managed
        images = await generate_image_routed_managed(
            model_key=spec.key, prompt=prompt, cfg=cfg,
            direct_fn=lambda: generate_image(spec.key, prompt, cfg),
        )
    except ProviderUnavailable:
        await _refund(session, user, budget, cost, credits_charged=qcredits,
                      was_premium=qwas_premium)  # FIX: B9
        await wait.edit_text(_("gen.unavailable_refund"))
        return
    except Exception:  # noqa: BLE001
        await _refund(session, user, budget, cost, credits_charged=qcredits,
                      was_premium=qwas_premium)  # FIX: B9
        await wait.edit_text(_("gen.error_refund"))
        return

    # Refund any variants the provider did not actually return (charged-for-requested,
    # reconciled on delivery), so the user never pays for images they didn't get.
    missing = count - len(images)
    if missing > 0:
        # FIX: C8 - pass credits_charged + was_premium so the partial refund lands in
        # the same budget (✨ balance) as the original charge, not the quota counter.
        await _refund(session, user, budget, per * missing,
                      credits_charged=per * missing if qcredits else 0,
                      was_premium=qwas_premium)

    # FIX: X2 - suppress TelegramBadRequest if the "please wait" message was already
    # deleted by the user/admin — without this, the exception propagates and the image
    # delivery loop never runs (user charged, no image delivered, no refund).
    with contextlib.suppress(Exception):
        await wait.delete()
    # remember the prompt so «ещё вариант» can re-run without re-typing, and the
    # result URLs so «файл» can re-send them uncompressed (full quality, ТЗ §5).
    urls = [img.url for img in images if img.url]
    await state.update_data(last_prompt=prompt, last_image_urls=urls)
    for i, img in enumerate(images):
        kb = _postgen_kb(_, has_file=bool(urls)) if i == len(images) - 1 else None
        if img.url:
            await message.answer_photo(img.url, reply_markup=kb)
        elif img.data:
            await message.answer_photo(
                BufferedInputFile(img.data, filename="image.png"), reply_markup=kb
            )


@router.callback_query(F.data == "img:file")
async def cb_img_file(callback: CallbackQuery, state: FSMContext, _: Translator) -> None:
    """Re-send the last result(s) as uncompressed document(s) — full quality."""
    urls = (await state.get_data()).get("last_image_urls") or []
    if not urls:
        await callback.answer(_("img.no_prompt"), show_alert=True)
        return
    await callback.answer()
    for url in urls:
        try:
            await callback.message.answer_document(url)
        except Exception:  # noqa: BLE001 — a provider URL may not be re-fetchable
            await callback.message.answer(url, parse_mode=None)


@router.callback_query(PhotoSG.service_config, F.data == "img:more")
async def cb_img_more(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User, _: Translator
) -> None:
    data = await state.get_data()
    spec = PHOTO_SPECS.get(data.get("service", ""))
    prompt = data.get("last_prompt")
    if spec is None or not prompt:
        await callback.answer(_("img.no_prompt"), show_alert=True)
        return
    await callback.answer()
    await _run_photo(callback.message, state, session, user, spec, data["cfg"], prompt, _)


@router.callback_query(F.data == "img:upscale")
async def cb_img_upscale(callback: CallbackQuery, state: FSMContext, _: Translator) -> None:
    await callback.message.answer(_("upscale.intro"), reply_markup=_upscale_kb(_))
    await callback.answer()


@router.message(AvatarSG.awaiting_selfie, F.photo)
async def on_avatar_selfie(
    message: Message, state: FSMContext, session: AsyncSession, user: User, _: Translator
) -> None:
    file_id = message.photo[-1].file_id
    data = await state.get_data()
    job = GenerationJob(
        user_id=user.user_id,
        service="avatar",
        status="pending",
        # charge_id links this job to the exact Stars purchase, so a refund (no provider
        # yet) reverses the right tx even if the user bought avatar more than once.
        params={
            "selfie_file_id": file_id, "count": 100,
            "charge_id": data.get("avatar_charge_id"),
        },
    )
    session.add(job)
    await session.commit()
    await state.clear()
    # Enqueue so workers/avatar_tasks.py processes it; if the queue is down the
    # claim_pending_avatars cron sweeps it later. (No provider yet → the worker
    # refunds the Stars purchase rather than leaving the user charged.)
    try:
        from core.queue import is_priority_job

        await enqueue(
            "process_avatar_job", str(job.job_id),
            priority=await is_priority_job(session, job),
        )
    except Exception as exc:  # noqa: BLE001 — cron sweep will re-enqueue
        # FIX: AUDIT-114 - log instead of silent pass
        import structlog
        structlog.get_logger().warning(
            "avatar.enqueue_failed", job_id=str(job.job_id), error=str(exc))
    await message.answer(_("avatar.started"))


async def _refund(
    session: AsyncSession, user: User, budget: str, cost: int, *,
    credits_charged: int = 0, was_premium: bool | None = None,  # FIX: B9 - carry through
) -> None:
    if budget == "image":
        await packs.refund(session, user.user_id, "image", cost)
    else:
        await refund_text(session, user, cost, credits_charged=credits_charged,
                          was_premium=was_premium)  # FIX: B9
