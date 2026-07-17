"""Mini App REST endpoints (§11, §13). All routes authenticate via Telegram
WebApp initData (HMAC-verified in deps)."""
from __future__ import annotations

import hashlib
import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import current_webapp_user
from api.images import _validate_image
from core.ai_router.image_specs import PHOTO_SPECS
from core.ai_router.video_specs import VIDEO_SPECS
from core.constants import (
    CREDIT_PACKS,
    MINIAPP_PHOTO_CATEGORIES,
    MINIAPP_PHOTO_RATIOS,
    PACK_PRICES,
    SUBSCRIPTION_PRICES,
)
from core.db import get_read_session, get_session
from core.models import (
    GenerationJob,
    MiniAppPhotoEffect,
    MiniAppVideoEffect,
    PackBalance,
    User,
)
from core.queue import enqueue
from core.services import credits, moderation, pricing, storage
from core.services.quota import (
    miniapp_quota_state,
    sponsored_free_remaining,
    try_consume_miniapp_free,
    try_consume_sponsored_free,
)
from core.services.refunds import refund_job
from core.services.service_config import effective_options
from core.services.users import get_or_create_user

router = APIRouter(tags=["miniapp"])

MAX_UPLOAD = 30 * 1024 * 1024  # 30 MB per photo (§13.3)
# Cap the COMBINED size of a multi-photo effect request so one call can't pin the
# API worker's memory by uploading many max-size photos at once (§13.3).
MAX_UPLOAD_TOTAL = 60 * 1024 * 1024

# FIX: AUDIT-U3 - window (seconds) for collapsing a double-tap into one generation.
# A double-submit (DOM Generate button + Telegram MainButton both fire run()) lands
# within milliseconds; 8s comfortably covers it while barely affecting a user who
# deliberately re-runs the SAME effect+photo+prompt. The key is released on any
# pre-commit failure, so a genuine retry after an error is never locked out.
_GEN_DEDUP_TTL = 8

# Persisted user uploads (selfies for img2img effects). Stored in S3/MinIO when
# configured (so every API replica + the worker + external providers can fetch
# them by URL), with a local-disk fallback for zero-infra dev — see
# core.services.storage. The local fallback is served at /media/uploads/<file>
# (api.main mounts ../media at /media). Uploads are validated by content in
# _validate_image, so the client's filename extension is not trusted.


async def _enqueue_or_refund(session: AsyncSession, job: GenerationJob, worker: str) -> None:
    """Enqueue the job; if the queue (Redis) is unavailable, mark the job failed,
    refund whatever was charged, and surface 503 instead of a 500 + stuck job.

    Premium-owned jobs jump the queue (ТЗ §8) when admin-enabled."""
    from core.queue import is_priority_job

    try:
        await enqueue(worker, str(job.job_id), priority=await is_priority_job(session, job))
    except Exception as exc:  # noqa: BLE001 — queue/Redis down
        job.status = "failed"
        job.error = f"queue unavailable: {exc}"
        # Canonical reversal (🪙 / pack / free slot) — single source of truth, so
        # this never drifts from the worker/sweep refund paths.
        await refund_job(session, job)
        await session.commit()
        raise HTTPException(
            status_code=503, detail="generation queue unavailable, try again"
        ) from exc


# ---- Higgsfield-style effect presets ---------------------------------------
_KIND_MODEL = {"photo": MiniAppPhotoEffect, "video": MiniAppVideoEffect}
_KIND_SPECS = {"photo": PHOTO_SPECS, "video": VIDEO_SPECS}
# Trends is a highlight reel (curated + organically popular), not the whole catalog.
_TRENDING_LIMIT = 30
# Mini App effect kind -> routing modality (for provider-availability detection).
_KIND_MODALITY = {"photo": "image", "video": "video"}


def _direct_provider_available(kind: str) -> bool:
    """True if at least one DIRECT (env-key) provider for this effect kind can
    generate right now — i.e. a real adapter with its key configured (stubs report
    unavailable). The aggregator path is checked separately against the DB."""
    if kind == "photo":
        from core.ai_router.image_adapters import _IMAGE_PROVIDERS

        return any(p.is_available() for p in _IMAGE_PROVIDERS.values())
    from core.ai_router.video_adapters import provider_for

    for key in VIDEO_SPECS:
        p = provider_for(key)
        if p is not None and p.is_available():
            return True
    return False


# FIX: PERF-A1 - the Mini App storefront sections are recomputed on every /profile
# load (the hottest endpoint), and the "auto" path issues a candidate_accounts DB
# query per modality. Provider availability + the admin section override change
# rarely, so cache the whole (global, not per-user) result in Redis for a short TTL.
# A load-test showed /profile at p99 ~8s under 100-way concurrency, dominated by
# this uncached fan-out. Staleness is bounded by the TTL; set_config invalidates it
# on an admin section-override change.
_SECTIONS_CACHE_KEY = "cache:miniapp_sections"
_SECTIONS_CACHE_TTL = 30  # seconds


async def _miniapp_sections(session: AsyncSession) -> dict[str, bool]:
    """Which effect segments (photo/video) the Mini App should show. Hybrid: the
    admin ``miniapp_sections`` override ("on"/"off") wins; "auto" (default) shows a
    segment only when a working provider exists for its modality — a configured
    Kie/MuAPI aggregator account OR a direct env-key adapter — so the storefront
    never offers an effect that could only refund.

    Redis-cached (best-effort, TTL ``_SECTIONS_CACHE_TTL``) so a burst of profile
    loads doesn't re-query provider availability every time. Any Redis hiccup falls
    through to a live recompute."""
    from core.redis_client import redis_client

    try:
        raw = await redis_client.get(_SECTIONS_CACHE_KEY)
        if raw:
            return json.loads(raw)
    except Exception:  # noqa: BLE001 — cache is best-effort
        pass

    from core.services import ai_routing as routing

    cfg = await pricing.get_config(session)
    override = cfg.get("miniapp_sections") or {}
    out: dict[str, bool] = {}
    for kind, modality in _KIND_MODALITY.items():
        mode = override.get(kind, "auto")
        if mode == "on":
            out[kind] = True
        elif mode == "off":
            out[kind] = False
        else:
            accounts = await routing.candidate_accounts(session, modality)
            out[kind] = bool(accounts) or _direct_provider_available(kind)

    try:
        await redis_client.set(_SECTIONS_CACHE_KEY, json.dumps(out), ex=_SECTIONS_CACHE_TTL)
    except Exception:  # noqa: BLE001 — cache is best-effort
        pass
    return out


async def _load_preset(session: AsyncSession, kind: str, effect_id: int):
    model = _KIND_MODEL.get(kind)
    if model is None:
        raise HTTPException(status_code=404, detail="unknown effect kind")
    row = await session.get(model, effect_id)
    if row is None or not row.enabled:
        raise HTTPException(status_code=404, detail="effect not found")
    return row


def _allowed_models(row) -> list[str]:
    models = [m for m in [row.recommended_model] if m]
    for m in row.compatible_models or []:
        if m and m not in models:
            models.append(m)
    return models


def _model_card(kind: str, model_key: str, override: dict | None = None) -> dict | None:
    spec = _KIND_SPECS[kind].get(model_key)
    if spec is None:
        return None
    # Same admin option lists + money-guard the bot keyboards use, so the Mini App
    # create screen shows the admin's configured options (and hidden toggles), not
    # the raw spec — the surfaces stay in sync.
    eff = effective_options(spec, override)
    card: dict = {"key": model_key, "title": spec.title, "default": spec.default}
    for attr in ("models", "qualities", "ratios", "durations", "resolutions"):
        val = getattr(eff, attr)
        if val:
            card[attr] = val
    if eff.modes and "modes" not in eff.hide:
        card["modes"] = eff.modes
    for flag, token in (("audio", "audio"), ("fourk", "fourk"),
                        ("seed", "seed"), ("prompt_enhance", "enhance")):
        if getattr(spec, flag, False) and token not in eff.hide:
            card[flag] = True
    return card


def _compute_cost(kind: str, model_key: str, params: dict) -> int:
    spec = _KIND_SPECS[kind].get(model_key)
    if spec is None:
        return 1
    try:
        return max(1, int(spec.cost(params or {})))
    except Exception:  # noqa: BLE001 — defensive: any bad param falls back to 1
        return 1


def _price_override(row, default: int) -> int:
    """The admin's per-effect price override (row.price > 0) or the given default.
    Single source of truth for effect pricing across preset + legacy endpoints."""
    override = getattr(row, "price", 0) or 0
    return int(override) if override > 0 else default


def _effect_price(kind: str, row, model_key: str, params: dict) -> int:
    """Final price for an effect: admin override wins, else the spec's cost."""
    return _price_override(row, _compute_cost(kind, model_key, params))


async def _effective_user_price(session, user, kind: str, row, model_key: str, params: dict) -> int:
    """Price THIS user pays right now: 0 for a sponsored effect while they still have
    a free sponsored generation today (the sponsor pays), else the normal price."""
    base = _effect_price(kind, row, model_key, params)
    if getattr(row, "is_ad", False):
        cap = await pricing.sponsored_free_daily(session)
        if cap > 0 and sponsored_free_remaining(user, cap) > 0:
            return 0
    return base


def _preset_card(kind: str, row) -> dict:
    return {
        "id": row.effect_id,
        "kind": kind,
        "name": row.name_ru,
        "author": row.author,
        "category": row.category,
        "badge": getattr(row, "badge", None),
        "is_ad": getattr(row, "is_ad", False),
        "preview_url": row.preview_url or row.thumbnail_url,
        "recommended_model": row.recommended_model,
        "price": _effect_price(kind, row, row.recommended_model, row.default_params or {}),
    }


async def _require_user(session: AsyncSession, tg: dict) -> User:
    # Opening the Mini App registers the user (same as /start in the bot).
    user, _created = await get_or_create_user(
        session, tg["id"], tg.get("username"), tg.get("language_code")
    )
    return user


@router.get("/profile")
async def profile(
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    user = await _require_user(session, tg)
    balances = await session.get(PackBalance, user.user_id)
    q = await miniapp_quota_state(session, user)
    return {
        "user_id": user.user_id,
        "sub_tier": user.sub_tier,
        "is_premium": user.is_premium,
        "credits": user.credits,
        # FIX: AUDIT12-F8 - expose language_code so the Mini App can sync its UI
        # language with the bot (the user picked it via /language in Telegram).
        "language_code": user.language_code or "ru",
        "mini_app_quota": {"used": q.used, "limit": q.limit},
        "balances": {
            "image": balances.image_credits if balances else 0,
            "video": balances.video_credits if balances else 0,
            "music": balances.music_credits if balances else 0,
        },
        # Which effect segments to show (provider-aware + admin override) so the app
        # hides a kind that has no working provider.
        "sections": await _miniapp_sections(session),
    }


# FIX: AUDIT12-21 - GDPR Art. 17 self-service deletion endpoint.
@router.delete("/me/delete")
async def delete_my_account(
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Permanently delete the caller's account and all their data."""
    from core.services.gdpr import delete_user_data
    user = await _require_user(session, tg)
    counts = await delete_user_data(session, user.user_id)
    await session.commit()
    return {"ok": True, "user_id": user.user_id, "deleted": counts}


@router.get("/bonus")
async def bonus_status(
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Daily login-streak bonus state for the Mini App profile card."""
    from core.services import daily_bonus

    user = await _require_user(session, tg)
    s = daily_bonus.status(user)
    return {"can_claim": s.can_claim, "streak": s.streak, "next_amount": s.next_amount}


@router.post("/bonus/claim")
async def bonus_claim(
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Claim today's bonus (idempotent per UTC day). Returns the new balance so the
    card can refresh without a second round-trip."""
    from core.services import daily_bonus

    user = await _require_user(session, tg)
    r = await daily_bonus.claim(session, user)
    return {
        "claimed": r.claimed,
        "amount": r.amount,
        "streak": r.streak,
        "already_today": r.already_today,
        "credits": user.credits,
    }


@router.get("/referrals")
async def referrals_me(
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The user's referral link + invited count + 🪙 earned, for the profile card."""
    from sqlalchemy import func

    from core.bot_client import get_bot
    from core.models import Referral

    user = await _require_user(session, tg)
    invited = (await session.scalar(
        select(func.count()).select_from(User).where(User.referred_by == user.user_id)
    )) or 0
    earned = (await session.scalar(
        select(func.coalesce(func.sum(Referral.reward_amount), 0))
        .where(Referral.referrer_id == user.user_id)
    )) or 0
    try:
        me = await get_bot().get_me()
        link = f"https://t.me/{me.username}?start=ref_{user.user_id}"
    except Exception:  # noqa: BLE001 — link is best-effort
        link = ""
    return {"link": link, "invited": int(invited), "earned": int(earned)}


class PromoReq(BaseModel):
    code: str


@router.post("/promo")
async def redeem_promo(
    req: PromoReq,
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # FIX: AUDIT-14 - rate limit promo redemption (10/hour/user) to prevent brute-force
    from core.services import ratelimit
    try:
        if not await ratelimit.allow(f"miniapp:promo:{tg['id']}", 10, 3600):
            raise HTTPException(status_code=429, detail="rate limit")
    except HTTPException:
        raise
    except Exception:
        pass  # fail-open on Redis down
    """Redeem a promo code from the Mini App (parity with the bot's /promo)."""
    from core.services import promos

    user = await _require_user(session, tg)
    if user.is_banned:
        raise HTTPException(status_code=403, detail="banned")
    code = (req.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="empty code")
    # Capture the balance BEFORE redeem: every rejection path in promos.redeem
    # (invalid / already / expired / misconfigured) calls session.rollback(), which
    # EXPIRES `user`. Reading user.credits afterwards would trigger a sync lazy-load
    # on the async session and raise MissingGreenlet (a 500 on any wrong code — and
    # it's DB-agnostic, not just SQLite). On the success path the commit leaves
    # user.credits fresh (expire_on_commit=False); on rejection nothing changed.
    credits_before = user.credits
    result = await promos.redeem(session, user, code)
    return {
        "ok": bool(result.ok),
        "status": result.status,
        "amount": result.amount,
        "reward_type": result.reward_type,
        "credits": user.credits if result.ok else credits_before,
    }


@router.get("/photo-effects")
async def photo_effects(
    category: str = "all",
    tg=Depends(current_webapp_user),
    # PERF: pure catalog read (no user creation / no writes) → route to the read
    # replica when configured (DATABASE_READ_URL); falls back to primary otherwise.
    session: AsyncSession = Depends(get_read_session),
) -> list[dict]:
    stmt = select(MiniAppPhotoEffect).where(MiniAppPhotoEffect.enabled.is_(True))
    if category != "all":
        stmt = stmt.where(MiniAppPhotoEffect.category == category)
    stmt = stmt.order_by(MiniAppPhotoEffect.sort_order, MiniAppPhotoEffect.gen_count.desc())
    rows = (await session.scalars(stmt)).all()
    return [
        {
            "id": e.effect_id,
            "name": e.name_ru,
            "category": e.category,
            "thumbnail": e.thumbnail_url,
            "badge": e.badge,
            "is_ad": e.is_ad,
        }
        for e in rows
    ]


@router.get("/video-effects")
async def video_effects(
    category: str = "all",
    tg=Depends(current_webapp_user),
    # PERF: pure catalog read → read replica when configured (see photo_effects).
    session: AsyncSession = Depends(get_read_session),
) -> list[dict]:
    stmt = select(MiniAppVideoEffect).where(MiniAppVideoEffect.enabled.is_(True))
    if category != "all":
        stmt = stmt.where(MiniAppVideoEffect.category == category)
    stmt = stmt.order_by(MiniAppVideoEffect.sort_order, MiniAppVideoEffect.gen_count.desc())
    rows = (await session.scalars(stmt)).all()
    return [
        {
            "id": e.effect_id,
            "name": e.name_ru,
            "category": e.category,
            "provider": e.provider,
            "thumbnail": e.thumbnail_url,
        }
        for e in rows
    ]


@router.get("/categories")
async def categories(tg=Depends(current_webapp_user)) -> dict:
    return {"photo": MINIAPP_PHOTO_CATEGORIES}


@router.get("/photo-ratios")
async def photo_ratios(tg=Depends(current_webapp_user)) -> list[str]:
    return MINIAPP_PHOTO_RATIOS


@router.get("/banners")
async def banners(
    locale: str | None = None,
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Carousel slides + rotation interval for the Mini App home screen.
    Fully admin-managed (api.admin.banners). Locale targeting: a slide with a NULL
    locale shows to everyone; a slide with a locale shows only to users on that
    language (the Mini App passes its current ``locale``). No locale param → all
    enabled slides (back-compat for older clients)."""
    from sqlalchemy import or_

    from core.models import MiniAppBanner, Pricing

    stmt = select(MiniAppBanner).where(MiniAppBanner.enabled.is_(True))
    if locale:
        # 2-letter language only; ignore region suffixes the client might send.
        loc = locale.split("-")[0].lower()[:8]
        stmt = stmt.where(or_(MiniAppBanner.locale.is_(None), MiniAppBanner.locale == loc))
    rows = (await session.scalars(
        stmt.order_by(MiniAppBanner.sort_order, MiniAppBanner.id)
    )).all()
    row = await session.get(Pricing, "miniapp_carousel")
    value = (row.value or {}) if row else {}
    try:
        interval_ms = int(value.get("interval_ms", 5000))
    except (TypeError, ValueError):
        interval_ms = 5000
    interval_ms = max(1500, min(60000, interval_ms))
    # Render behaviour (animation/autoplay/loop/indicators/arrows/swipe/speed) is
    # admin-managed; sanitize so the Mini App always gets a complete, valid object.
    from api.carousel import _sanitize_behavior

    return {
        "interval_ms": interval_ms,
        "behavior": _sanitize_behavior(value.get("behavior")),
        "slides": [
            {
                "id": b.id,
                "image_url": b.image_url,
                "title": b.title,
                "subtitle": b.subtitle,
                "link_url": b.link_url,
            }
            for b in rows
            if b.image_url
        ],
    }


# Collapse repeat impressions/clicks from the same viewer within this window so the
# counters approximate unique reach (a carousel re-shows the same slide many times
# per session) and can't be trivially inflated by hammering the endpoint.
_BANNER_TRACK_TTL = 6 * 3600


async def _track_banner(
    session: AsyncSession, banner_id: int, viewer_id: int, column: str
) -> None:
    """Atomic +1 on a banner ``column`` counter (``impressions``/``clicks``), deduped
    per viewer per 6h. The column is the single discriminator — it names both the
    dedupe namespace and the counter, so the two can't drift. An unknown banner id is
    a silent no-op so tracking never breaks the UI."""
    from core.models import MiniAppBanner
    from core.redis_client import first_seen

    if not await first_seen(f"bnr:{column}:{viewer_id}:{banner_id}", _BANNER_TRACK_TTL):
        return  # already counted this viewer recently
    await session.execute(
        update(MiniAppBanner)
        .where(MiniAppBanner.id == banner_id)
        .values({column: getattr(MiniAppBanner, column) + 1})
    )
    await session.commit()


@router.post("/banners/{banner_id}/impression")
async def banner_impression(
    banner_id: int,
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Count one carousel-slide impression. Fire-and-forget from the Mini App."""
    await _track_banner(session, banner_id, tg["id"], "impressions")
    return {"ok": True}


@router.post("/banners/{banner_id}/click")
async def banner_click(
    banner_id: int,
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Count one carousel-slide tap. CTR = clicks / impressions."""
    await _track_banner(session, banner_id, tg["id"], "clicks")
    return {"ok": True}


# ---- Unified preset catalog (Higgsfield-style) -----------------------------
@router.get("/effects")
async def list_effects(
    kind: str = "photo",
    category: str = "all",
    trending: bool = False,
    tg=Depends(current_webapp_user),
    # PERF: pure catalog read → read replica when configured (see photo_effects).
    session: AsyncSession = Depends(get_read_session),
) -> list[dict]:
    model = _KIND_MODEL.get(kind)
    if model is None:
        raise HTTPException(status_code=404, detail="unknown effect kind")
    stmt = select(model).where(model.enabled.is_(True))
    if trending:
        # Hybrid Trends: admin-curated (is_trending) effects PLUS organically
        # popular ones (gen_count > 0), curated first then by real usage. An effect
        # that is neither flagged nor ever generated isn't "trending", so it's
        # excluded; the set is capped so Trends stays a highlight reel, not the
        # whole catalog.
        from sqlalchemy import or_

        stmt = (
            stmt.where(or_(model.is_trending.is_(True), model.gen_count > 0))
            .order_by(
                model.is_ad.desc(), model.is_trending.desc(),
                model.gen_count.desc(), model.sort_order,
            )
            .limit(_TRENDING_LIMIT)
        )
    else:
        if category != "all":
            stmt = stmt.where(model.category == category)
        # Sponsored (is_ad) effects are promoted to the top of the grid.
        stmt = stmt.order_by(model.is_ad.desc(), model.sort_order, model.gen_count.desc())
    rows = (await session.scalars(stmt)).all()
    return [_preset_card(kind, r) for r in rows]


@router.get("/effects/{kind}/{effect_id}")
async def effect_detail(
    kind: str,
    effect_id: int,
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    user = await _require_user(session, tg)
    row = await _load_preset(session, kind, effect_id)
    svc_opts = await pricing.service_options(session)
    models = [c for m in _allowed_models(row) if (c := _model_card(kind, m, svc_opts.get(m)))]
    default_model = row.recommended_model or (models[0]["key"] if models else None)
    price = await _effective_user_price(
        session, user, kind, row, default_model, row.default_params or {}
    )
    return {
        "id": row.effect_id,
        "kind": kind,
        "name": row.name_ru,
        "author": row.author,
        "category": row.category,
        "preview_url": row.preview_url or row.thumbnail_url,
        "max_photos": row.max_photos,
        "prompt_mode": getattr(row, "prompt_mode", "optional"),
        "recommended_model": default_model,
        "default_params": row.default_params or {},
        "models": models,
        "price": price,
    }


class CostRequest(BaseModel):
    model: str
    params: dict = {}


class ParamsRequest(BaseModel):
    # Body for the free-model cost endpoint — the model is in the URL path, so only
    # the generation params ride in the body.
    params: dict = {}


@router.post("/effects/{kind}/{effect_id}/cost")
async def effect_cost(
    kind: str,
    effect_id: int,
    req: CostRequest,
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    user = await _require_user(session, tg)
    row = await _load_preset(session, kind, effect_id)
    model = req.model if req.model in _allowed_models(row) else row.recommended_model
    cost = await _effective_user_price(session, user, kind, row, model, req.params)
    return {"cost": cost, "currency": "credits"}


@router.post("/effects/{kind}/{effect_id}/generate")
async def effect_generate(
    kind: str,
    effect_id: int,
    model: str = Form(...),
    params: str = Form("{}"),
    prompt: str = Form(""),
    idempotency_key: str = Form(""),  # FIX: AUDIT-U3 - per-submit-intent dedup token
    photos: list[UploadFile] = File(default=[]),
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # FIX: AUDIT-107 - rate limit effect generation (20/min/user)
    from core.services import ratelimit
    try:
        if not await ratelimit.allow(f"miniapp:gen:{tg['id']}", 20, 60):
            raise HTTPException(status_code=429, detail="rate limit")
    except HTTPException:
        raise
    except Exception:
        pass  # fail-open on Redis down
    user = await _require_user(session, tg)
    if user.is_banned:
        raise HTTPException(status_code=403, detail="banned")

    row = await _load_preset(session, kind, effect_id)
    if model not in _allowed_models(row):
        model = row.recommended_model
    try:
        cfg = json.loads(params) if params else {}
        if not isinstance(cfg, dict):
            cfg = {}
    except json.JSONDecodeError:
        cfg = {}

    # Per-effect prompt policy (admin-set): a hidden-prompt effect is pure style, so
    # the user's text is IGNORED (and can't be used to smuggle an off-style prompt);
    # a required-prompt effect must carry non-empty text.
    prompt_mode = getattr(row, "prompt_mode", "optional")
    user_prompt = (prompt or "").strip()
    if prompt_mode == "hidden":
        user_prompt = ""
    elif prompt_mode == "required" and not user_prompt:
        raise HTTPException(status_code=400, detail="prompt required for this effect")

    # Compose the hidden style prompt with the user's text and MODERATE it BEFORE
    # any work — the Mini App is a free-text input path like the bot, so it must
    # honour the same content rules (parity with the bot handlers). Omitting this
    # was a moderation bypass (free text → generation with no content check).
    template = row.prompt_template or "{prompt}"
    final_prompt = template.replace("{prompt}", user_prompt).strip()
    if not (await moderation.moderate(final_prompt)).allowed:
        raise HTTPException(status_code=400, detail="prompt blocked by moderation")

    # Validate uploads (count + per-file + combined size) and decode-check them by
    # CONTENT up front, but DON'T persist yet: save only AFTER a successful charge,
    # so a blocked/unpaid request never leaves orphaned objects in storage.
    photos = photos or []
    if len(photos) > row.max_photos:
        raise HTTPException(status_code=400, detail=f"max {row.max_photos} photos")
    pending: list[tuple[bytes, str]] = []
    total = 0
    for ph in photos:
        data = await ph.read()
        total += len(data)
        if len(data) > MAX_UPLOAD or total > MAX_UPLOAD_TOTAL:
            raise HTTPException(status_code=413, detail="upload too large")
        pending.append((data, _validate_image(data)))

    cost = _effect_price(kind, row, model, cfg)

    # FIX: AUDIT-U3 - idempotent submit guard. The Mini App wires run() to BOTH the DOM
    # Generate button and the Telegram MainButton, and the client phase guard is not
    # synchronous, so a fast double-tap can fire two requests. The client stamps ONE
    # ``idempotency_key`` per submit intent (stable across the double-tap twins), and
    # the backend admits only the first: the duplicate gets 409, no second job/charge.
    # Keying on the client token — NOT on request content — is deliberate: a user is
    # allowed to generate the SAME effect+photo+prompt again (e.g. to consume a daily
    # sponsored-free cap), which a content hash would wrongly block. When no token is
    # sent (older clients) the guard is skipped, so behaviour is unchanged. first_seen
    # is an atomic SETNX that fails OPEN on Redis down (a blip must never block a real
    # generation). Released on any pre-commit failure so a genuine retry isn't locked
    # out for the window.
    from core.redis_client import first_seen, redis_client
    # isinstance guard: when the endpoint is invoked directly (unit tests) rather than
    # over HTTP, an unpassed Form() default arrives as the sentinel object, not a str —
    # treat that (and any non-str) as "no idempotency key".
    idem = (idempotency_key if isinstance(idempotency_key, str) else "").strip()[:100]
    dedup_key = (
        "miniapp:gen:dedup:" + hashlib.sha256(
            f"{user.user_id}|{idem}".encode()
        ).hexdigest()
    ) if idem else None
    if dedup_key is not None and not await first_seen(dedup_key, _GEN_DEDUP_TTL):
        raise HTTPException(status_code=409, detail="duplicate submit — already generating")

    async def _release_dedup() -> None:
        """Free the dedup key so a real retry after a pre-commit failure isn't blocked
        (the double-tap twin was already rejected by the SETNX above). No-op when the
        client sent no idempotency key."""
        if dedup_key is None:
            return
        try:
            await redis_client.delete(dedup_key)
        except Exception:  # noqa: BLE001 — best-effort release
            pass

    # Charge WITHOUT committing yet (commit=False), then commit the charge together
    # with the job row in ONE transaction below — so a hard crash between them can
    # never burn a free slot / 🪙 with no job to show for it. On any failure before
    # that commit, a rollback undoes the still-uncommitted charge: balance untouched,
    # nothing to refund.
    #
    # Charge precedence: a SPONSORED effect is free up to the admin daily cap (the
    # sponsor pays) → else a photo effect's free weekly slot → else ✨ credits.
    sponsored_free = False
    used_free = False
    pack_type = "credits"
    if getattr(row, "is_ad", False):
        cap = await pricing.sponsored_free_daily(session)
        sponsored_free = await try_consume_sponsored_free(session, user, cap, commit=False)
    if sponsored_free:
        pack_type, cost = None, 0
    else:
        if kind == "photo":
            used_free = await try_consume_miniapp_free(session, user, commit=False)
        if used_free:
            pack_type, cost = None, 0
        elif not await credits.try_consume(session, user, cost, commit=False):
            await session.rollback()
            await _release_dedup()
            raise HTTPException(status_code=402, detail="not enough credits — top up ✨")

    # Persist the inputs while the charge is still uncommitted (it holds its row
    # lock). If storage fails, roll the charge back — nothing was committed.
    try:
        input_images = [
            await storage.save_upload(d, e, prefix="uploads") for d, e in pending
        ]
    except Exception as exc:  # noqa: BLE001 — storage/network failure
        await session.rollback()
        await _release_dedup()
        raise HTTPException(status_code=503, detail="upload failed") from exc

    job_params = {**cfg, "prompt": final_prompt, "preset_id": effect_id,
                  "photo_count": len(photos), "input_images": input_images,
                  "free": used_free, "sponsored_free": sponsored_free}
    # FIX: AI-10 - `input_images` is a list of S3/MinIO URLs (from save_upload).
    # The video worker (workers/video_tasks.py, AI-16 fix) reads input_images[0]
    # and injects it as `image_url` for Kling's image2video endpoint. The photo
    # worker reads input_images as `image_refs` for Gemini img2img.
    # photo effects run on the shared photoeffect worker (model in model_variant);
    # video effects route by service key so provider_for() resolves the provider.
    service = "photoeffect" if kind == "photo" else model
    job = GenerationJob(
        user_id=user.user_id,
        service=service,
        model_variant=model,
        params=job_params,
        cost_credits=cost,
        pack_type=pack_type,
        status="pending",
    )
    try:
        session.add(job)
        row.gen_count += 1
        await session.commit()  # charge + job land atomically
    except Exception as exc:  # noqa: BLE001 — never keep a charge for a job that wasn't created
        await session.rollback()
        await _release_dedup()
        raise HTTPException(status_code=503, detail="could not start generation") from exc

    worker = "process_photoeffect_job" if kind == "photo" else "process_video_job"
    await _enqueue_or_refund(session, job, worker)
    return {"job_id": str(job.job_id), "status": "pending", "cost": cost}


# ---- Free model choice (Higgsfield-style §6/§7): pick a model directly, not via a
# curated preset. The model IS a VIDEO_SPECS / PHOTO_SPECS entry, so cards, dynamic
# settings and pricing reuse the exact preset helpers — just without a DB row. These
# jobs carry a `free_model` marker (in place of `preset_id`) so History + the workers
# recognise them as in-app Mini App generations. -----------------------------------

def _free_max_photos(kind: str, spec) -> int:
    """How many reference photos a free-choice model accepts."""
    if kind == "photo":
        return 0 if getattr(spec, "text_only", False) else int(getattr(spec, "input_limit", 1) or 0)
    return 1 if getattr(spec, "image_input", False) else 0


@router.get("/models/{kind}")
async def free_models(
    kind: str,
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Every model the user can pick directly for this kind, with its settings card
    and base price. Read-only — no charge, no side effects."""
    await _require_user(session, tg)
    specs = _KIND_SPECS.get(kind)
    if specs is None:
        raise HTTPException(status_code=404, detail="unknown kind")
    svc_opts = await pricing.service_options(session)
    out: list[dict] = []
    for key, spec in specs.items():
        card = _model_card(kind, key, svc_opts.get(key))
        if card is None:
            continue
        out.append({
            "key": key,
            "kind": kind,
            "title": spec.title,
            "description": getattr(spec, "description", ""),
            "max_photos": _free_max_photos(kind, spec),
            "price": _compute_cost(kind, key, spec.default or {}),
            "default_params": spec.default or {},
            "card": card,
        })
    return out


@router.post("/models/{kind}/{model}/cost")
async def free_model_cost(
    kind: str,
    model: str,
    req: ParamsRequest,
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _require_user(session, tg)
    if kind not in _KIND_SPECS or model not in _KIND_SPECS[kind]:
        raise HTTPException(status_code=404, detail="unknown model")
    return {"cost": _compute_cost(kind, model, req.params), "currency": "credits"}


@router.post("/models/{kind}/{model}/generate")
async def free_model_generate(
    kind: str,
    model: str,
    params: str = Form("{}"),
    prompt: str = Form(""),
    idempotency_key: str = Form(""),  # FIX: AUDIT-U3 - per-submit-intent dedup token
    photos: list[UploadFile] = File(default=[]),
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Rate limit shares the effect budget (20/min/user).
    from core.services import ratelimit
    try:
        if not await ratelimit.allow(f"miniapp:gen:{tg['id']}", 20, 60):
            raise HTTPException(status_code=429, detail="rate limit")
    except HTTPException:
        raise
    except Exception:
        pass  # fail-open on Redis down

    user = await _require_user(session, tg)
    if user.is_banned:
        raise HTTPException(status_code=403, detail="banned")
    spec = _KIND_SPECS.get(kind, {}).get(model)
    if spec is None:
        raise HTTPException(status_code=404, detail="unknown model")

    try:
        cfg = json.loads(params) if params else {}
        if not isinstance(cfg, dict):
            cfg = {}
    except json.JSONDecodeError:
        cfg = {}

    # Free choice = free-text prompt straight through (no hidden style template), but
    # STILL moderated — same content rules as every other free-text generation path.
    final_prompt = (prompt or "").strip()
    if not (await moderation.moderate(final_prompt)).allowed:
        raise HTTPException(status_code=400, detail="prompt blocked by moderation")

    max_photos = _free_max_photos(kind, spec)
    photos = photos or []
    if len(photos) > max_photos:
        raise HTTPException(status_code=400, detail=f"max {max_photos} photos")
    pending: list[tuple[bytes, str]] = []
    total = 0
    for ph in photos:
        data = await ph.read()
        total += len(data)
        if len(data) > MAX_UPLOAD or total > MAX_UPLOAD_TOTAL:
            raise HTTPException(status_code=413, detail="upload too large")
        pending.append((data, _validate_image(data)))

    cost = _compute_cost(kind, model, cfg)

    # FIX: AUDIT-U3 - same idempotent-submit guard as effect_generate (see the long note
    # there): admit only the first request carrying a given client token, so a double-tap
    # twin can't charge + queue the free-model generation twice. Skipped when no token is
    # sent; fails OPEN on Redis down; released on any pre-commit failure.
    from core.redis_client import first_seen, redis_client
    idem = (idempotency_key if isinstance(idempotency_key, str) else "").strip()[:100]
    dedup_key = (
        "miniapp:gen:dedup:" + hashlib.sha256(
            f"{user.user_id}|{idem}".encode()
        ).hexdigest()
    ) if idem else None
    if dedup_key is not None and not await first_seen(dedup_key, _GEN_DEDUP_TTL):
        raise HTTPException(status_code=409, detail="duplicate submit — already generating")

    async def _release_dedup() -> None:
        if dedup_key is None:
            return
        try:
            await redis_client.delete(dedup_key)
        except Exception:  # noqa: BLE001 — best-effort release
            pass

    # Charge WITHOUT committing (same atomic charge+job pattern as effect_generate,
    # minus sponsored — a free-choice model is a normal paid generation). Precedence:
    # a photo model's free weekly slot → else ✨ credits.
    used_free = False
    pack_type = "credits"
    if kind == "photo":
        used_free = await try_consume_miniapp_free(session, user, commit=False)
    if used_free:
        pack_type, cost = None, 0
    elif not await credits.try_consume(session, user, cost, commit=False):
        await session.rollback()
        await _release_dedup()
        raise HTTPException(status_code=402, detail="not enough credits — top up ✨")

    try:
        input_images = [
            await storage.save_upload(d, e, prefix="uploads") for d, e in pending
        ]
    except Exception as exc:  # noqa: BLE001 — storage/network failure
        await session.rollback()
        await _release_dedup()
        raise HTTPException(status_code=503, detail="upload failed") from exc

    # `free_model` stands in for `preset_id`: it marks the job as an in-app Mini App
    # generation (see jobs_history + the video/photo workers) without pointing at a
    # curated preset that doesn't exist for a free-choice model.
    job_params = {**cfg, "prompt": final_prompt, "free_model": model,
                  "photo_count": len(photos), "input_images": input_images,
                  "free": used_free}
    service = "photoeffect" if kind == "photo" else model
    job = GenerationJob(
        user_id=user.user_id,
        service=service,
        model_variant=model,
        params=job_params,
        cost_credits=cost,
        pack_type=pack_type,
        status="pending",
    )
    try:
        session.add(job)
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        await _release_dedup()
        raise HTTPException(status_code=503, detail="could not start generation") from exc

    worker = "process_photoeffect_job" if kind == "photo" else "process_video_job"
    await _enqueue_or_refund(session, job, worker)
    return {"job_id": str(job.job_id), "status": "pending", "cost": cost}


@router.get("/jobs")
async def jobs_history(
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Recent Mini App generations for the History tab.

    Match Mini App effect jobs by BOTH the legacy service literals AND a non-null
    ``preset_id`` param: the unified Higgsfield path (which the live UI uses) stores
    a VIDEO_SPECS key as ``service`` for video effects (the worker routes the
    provider by it), so a plain ``service == 'videoeffect'`` filter silently dropped
    every video effect from History. ``preset_id`` is the stable marker every Mini
    App effect job carries, regardless of which generation path created it; bot
    generations have no preset_id, so they stay out."""
    from sqlalchemy import or_

    rows = (await session.scalars(
        select(GenerationJob)
        .where(
            GenerationJob.user_id == tg["id"],
            or_(
                GenerationJob.service.in_(("photoeffect", "videoeffect")),
                # .as_string() renders dialect-correct text extraction (CAST on
                # SQLite, ->> on Postgres) so a MISSING key is SQL NULL — unlike a
                # bare JSON index, which SQLite JSON_QUOTEs to the string 'null'.
                GenerationJob.params["preset_id"].as_string().isnot(None),
                # Free-choice model generations carry `free_model` instead of a preset.
                GenerationJob.params["free_model"].as_string().isnot(None),
            ),
        )
        .order_by(GenerationJob.created_at.desc())
        .limit(30)
    )).all()
    return [
        {
            "id": str(j.job_id),
            # Photo effects run on the shared "photoeffect" service; everything else
            # in this list is a video effect (unified path stores the model key).
            "kind": "photo" if j.service == "photoeffect" else "video",
            # The preset this job ran, so History can offer "повторить" (re-open the
            # same effect). None for any legacy job without a recorded preset_id.
            "preset_id": (j.params or {}).get("preset_id"),
            # Free-choice model key (§ variant 3) so History can replay by model when
            # there is no preset. None for preset-based / legacy jobs.
            "model": (j.params or {}).get("free_model"),
            "status": j.status,
            "result_url": j.result_url,
            "created_at": j.created_at.isoformat(),
        }
        for j in rows
    ]


@router.get("/jobs/{job_id}")
async def job_status(
    job_id: str,
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # FIX: AUDIT-108 - rate limit job polling (60/min/user)
    from core.services import ratelimit
    try:
        if not await ratelimit.allow(f"miniapp:poll:{tg['id']}", 60, 60):
            raise HTTPException(status_code=429, detail="rate limit")
    except HTTPException:
        raise
    except Exception as exc:
        import structlog
        structlog.get_logger().warning('api.routers.miniapp.job_status_failed', error=str(exc))
        # FIX: AUDIT12-L1 - was silent except: pass
    try:
        job_pk = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="job not found") from None
    job = await session.get(GenerationJob, job_pk)
    if job is None or job.user_id != tg["id"]:
        raise HTTPException(status_code=404, detail="job not found")
    return {"status": job.status, "result_url": job.result_url, "error": job.error}


class InvoiceRequest(BaseModel):
    kind: str               # "sub" | "pack"
    product: str | None = None      # premium | premium_x2
    months: int | None = None
    pack: str | None = None         # image_pack | video_pack | music_pack
    qty: int | None = None


@router.post("/billing/invoice-link")
async def invoice_link(
    req: InvoiceRequest,
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a Telegram Stars invoice link for WebApp.openInvoice(). Payment
    completes in Telegram and the bot's successful_payment handler activates it.
    Prices are resolved from the live admin config (constants are the validity set)."""
    from aiogram.types import LabeledPrice

    from core.bot_client import get_bot

    price: int | None
    if req.kind == "sub" and req.product in SUBSCRIPTION_PRICES and req.months:
        price = await pricing.subscription_price(session, req.product, req.months)
        title = f"{req.product} {req.months} мес"
        payload = f"sub:{req.product}:{req.months}"
    elif req.kind == "pack" and req.pack in PACK_PRICES and req.qty:
        price = await pricing.pack_price(session, req.pack, req.qty)
        title = f"{req.pack} {req.qty}"
        payload = f"pack:{req.pack}:{req.qty}"
    elif req.kind == "credits" and req.qty in CREDIT_PACKS:
        price = await pricing.credit_pack_price(session, req.qty)
        title = f"✨ {req.qty}"
        payload = f"credits:{req.qty}"
    else:
        raise HTTPException(status_code=400, detail="bad invoice request")
    if price is None:
        raise HTTPException(status_code=400, detail="price unavailable")

    link = await get_bot().create_invoice_link(
        title=title,
        description=title,
        payload=payload,
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=price)],
    )
    return {"url": link}


# FIX: PERF-A1b - the billing storefront is a pure GLOBAL projection of the pricing
# config (identical for every user; `tg` is used only for auth). It fanned out into
# ~7 pricing reads (one get_config deserialize per pack + subscription + credits) on
# every Mini App billing-tab open. Cache the assembled payload in Redis for a short
# TTL; pricing.set_config invalidates it so an admin price/sale change applies live.
_OFFERS_CACHE_KEY = "cache:miniapp_offers"
_OFFERS_CACHE_TTL = 30  # seconds


async def _billing_offers_payload(session: AsyncSession) -> dict:
    """Assemble the (global) storefront offers dict, Redis-cached (best-effort)."""
    from core.redis_client import redis_client

    try:
        raw = await redis_client.get(_OFFERS_CACHE_KEY)
        if raw:
            return json.loads(raw)
    except Exception:  # noqa: BLE001 — cache is best-effort
        pass

    def _offers(m: dict[int, int]) -> list[dict]:
        # qty/months -> stars; skip non-positive prices so a 0 hides an offer.
        return [{"qty": q, "stars": s} for q, s in sorted(m.items()) if s > 0]

    packs = {p: _offers(await pricing.pack_prices_for(session, p)) for p in PACK_PRICES}
    premium = await pricing.subscription_prices(session, "premium")
    out = {
        "credits": _offers(await pricing.credit_packs(session)),
        "packs": packs,
        "premium": [{"months": q, "stars": s} for q, s in sorted(premium.items()) if s > 0],
    }

    try:
        await redis_client.set(_OFFERS_CACHE_KEY, json.dumps(out), ex=_OFFERS_CACHE_TTL)
    except Exception:  # noqa: BLE001 — cache is best-effort
        pass
    return out


@router.get("/billing/offers")
async def billing_offers(
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Admin-configured storefront for the Mini App: which credit/pack/Premium
    offers to show + their live Stars prices (sale-discounted). The Mini App
    renders THIS instead of hard-coding qty/months arrays, so the admin controls
    the store without a frontend release. Offers with no configured price are
    dropped (admin removed them) — the storefront is a pure projection of config."""
    await _require_user(session, tg)
    return await _billing_offers_payload(session)
