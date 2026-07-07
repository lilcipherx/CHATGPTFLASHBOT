"""Admin: Mini App effect-preset catalog CRUD (photo + video) and preview
upload. Moderators can edit; admins can delete. All mutations are audited."""
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core.db import get_session
from core.models import AdminUser, MiniAppPhotoEffect, MiniAppVideoEffect

router = APIRouter(prefix="/effects", tags=["admin-effects"])

_MODEL = {"photo": MiniAppPhotoEffect, "video": MiniAppVideoEffect}

_MEDIA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "media", "effects")
_MAX_PREVIEW = 30 * 1024 * 1024


def _detect_video_ext(data: bytes) -> str | None:
    """Canonical extension for the two preview video formats, by MAGIC BYTES:
    MP4/ISO-BMFF (``ftyp`` box at offset 4) and WebM/Matroska (EBML header). None for
    anything else, so the caller falls back to image handling."""
    if data[4:8] == b"ftyp":
        return ".mp4"
    if data[:4] == b"\x1a\x45\xdf\xa3":  # EBML (WebM/MKV container)
        return ".webm"
    return None


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _model_for(kind: str):
    model = _MODEL.get(kind)
    if model is None:
        raise HTTPException(status_code=404, detail="unknown effect kind")
    return model


def _effect_dict(kind: str, row) -> dict:
    return {
        "id": row.effect_id,
        "kind": kind,
        "name_ru": row.name_ru,
        "category": row.category,
        "provider": getattr(row, "provider", None),
        "recommended_model": row.recommended_model,
        "compatible_models": row.compatible_models or [],
        "prompt_template": row.prompt_template,
        "prompt_mode": getattr(row, "prompt_mode", "optional"),
        "default_params": row.default_params or {},
        "max_photos": row.max_photos,
        "preview_url": row.preview_url,
        "thumbnail_url": row.thumbnail_url,
        "badge": getattr(row, "badge", None),
        "is_ad": getattr(row, "is_ad", False),
        "author": row.author,
        "is_trending": row.is_trending,
        "enabled": row.enabled,
        "sort_order": row.sort_order,
        "price": getattr(row, "price", 0) or 0,
        # What the user is actually charged: the override when set, else the model
        # spec's auto-cost — so the admin can see the real price even on "авто".
        "effective_price": _effective_price(kind, row),
        "gen_count": row.gen_count,
    }


def _effective_price(kind: str, row) -> int:
    """The real per-effect price: admin override (>0) wins, else the recommended
    model's computed cost for the effect's default params. Mirrors the Mini App's
    _effect_price so the panel never disagrees with what the user pays."""
    override = getattr(row, "price", 0) or 0
    if override > 0:
        return int(override)
    from api.routers.miniapp import _compute_cost

    return _compute_cost(kind, row.recommended_model or "", row.default_params or {})


@router.get("/specs/{kind}")
async def model_specs(
    kind: str,
    admin: AdminUser = Depends(require_role("moderator")),
) -> dict:
    """Per-model parameter schema (quality/ratio/duration/res/mode options + 4K/audio/
    seed/enhance flags + defaults) for the given kind. The editor builds friendly
    controls from this instead of a raw-JSON box. Same source as the Mini App, so the
    admin form always matches what the user actually sees."""
    if kind not in _MODEL:
        raise HTTPException(status_code=404, detail="unknown effect kind")
    from api.routers.miniapp import _KIND_SPECS, _model_card

    out = {}
    for model_key in _KIND_SPECS[kind]:
        card = _model_card(kind, model_key)
        if card:
            out[model_key] = card
    return {"models": out}


@router.get("")
async def list_effects(
    kind: str = "photo",
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    model = _model_for(kind)
    rows = (await session.scalars(
        select(model).order_by(model.sort_order, model.effect_id)
    )).all()
    return [_effect_dict(kind, r) for r in rows]


class EffectUpsert(BaseModel):
    # FIX: AUDIT13-M10 - bound storefront strings shown to every Mini App user.
    name_ru: str = Field(..., max_length=200)
    category: str = Field("all", max_length=32)
    provider: str | None = Field(None, max_length=64)
    recommended_model: str | None = Field(None, max_length=64)
    compatible_models: list[str] = []
    prompt_template: str | None = Field(None, max_length=4000)
    prompt_mode: str = "optional"   # hidden | optional | required
    default_params: dict = {}
    max_photos: int = Field(1, ge=0, le=10)
    preview_url: str | None = Field(None, max_length=2048)
    thumbnail_url: str | None = Field(None, max_length=2048)
    badge: str | None = Field(None, max_length=32)
    is_ad: bool = False
    author: str | None = Field(None, max_length=100)
    is_trending: bool = False
    enabled: bool = True
    sort_order: int = 0
    price: int = Field(0, ge=0, le=1_000_000)   # per-effect 🪙 price override; 0 = use the model spec's cost


def _apply(kind: str, row, req: EffectUpsert) -> None:
    row.name_ru = req.name_ru
    row.category = req.category
    row.recommended_model = req.recommended_model
    row.compatible_models = req.compatible_models
    row.prompt_template = req.prompt_template
    row.prompt_mode = (
        req.prompt_mode if req.prompt_mode in ("hidden", "optional", "required")
        else "optional"
    )
    row.default_params = req.default_params
    row.max_photos = req.max_photos
    row.preview_url = req.preview_url
    row.thumbnail_url = req.thumbnail_url
    row.author = req.author
    row.is_trending = req.is_trending
    row.enabled = req.enabled
    row.sort_order = req.sort_order
    row.price = max(0, req.price)
    row.is_ad = req.is_ad   # sponsored flag — supported on both photo and video
    if kind == "photo":
        row.badge = req.badge
    else:
        row.provider = req.provider or req.recommended_model or "kling"


def _require_preview_to_enable(enabled: bool, preview_url, thumbnail_url) -> None:
    """An effect may only be ENABLED once it has a visual — an uploaded preview or a
    thumbnail — so the storefront never shows a blank tile for a live effect (ТЗ §13).
    Disabled drafts may exist without a preview; upload one, then enable."""
    if enabled and not (preview_url or thumbnail_url):
        raise HTTPException(
            status_code=400,
            detail="Добавьте превью эффекта, прежде чем включать его.",
        )


@router.post("")
async def create_effect(
    req: EffectUpsert, request: Request,
    kind: str = "photo",
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    model = _model_for(kind)
    _require_preview_to_enable(req.enabled, req.preview_url, req.thumbnail_url)
    # effect_id is an explicit (non auto-increment) PK, so allocate max+1 and retry
    # if a concurrent create grabbed the same id (unique-PK violation on flush).
    row = None
    for _attempt in range(3):
        next_id = (await session.scalar(select(func.max(model.effect_id)))) or 0
        row = model(effect_id=next_id + 1, gen_count=0)
        _apply(kind, row, req)
        session.add(row)
        try:
            await session.flush()
            break
        except IntegrityError:
            await session.rollback()
            row = None
    if row is None:
        raise HTTPException(status_code=409, detail="could not allocate effect id, retry")
    await audit(session, admin_id=admin.id, action="effect.create", target_type=f"{kind}_effect",
    target_id=str(row.effect_id), after={"name": req.name_ru}, ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return _effect_dict(kind, row)


@router.put("/{kind}/{effect_id}")
async def update_effect(
    kind: str, effect_id: int, req: EffectUpsert, request: Request,
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    model = _model_for(kind)
    row = await session.get(model, effect_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    _apply(kind, row, req)
    # Enforce on the RESULTING state (after _apply), so a preview uploaded via the
    # /preview endpoint and round-tripped in the payload counts.
    _require_preview_to_enable(row.enabled, row.preview_url, row.thumbnail_url)
    await audit(session, admin_id=admin.id, action="effect.update", target_type=f"{kind}_effect",
    target_id=str(effect_id), after={"enabled": req.enabled}, ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return _effect_dict(kind, row)


@router.delete("/{kind}/{effect_id}")
async def delete_effect(
    kind: str, effect_id: int, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    model = _model_for(kind)
    row = await session.get(model, effect_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    await session.delete(row)
    await audit(session, admin_id=admin.id, action="effect.delete", target_type=f"{kind}_effect",
    target_id=str(effect_id), ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return {"ok": True}


@router.post("/{kind}/{effect_id}/preview")
async def upload_preview(
    kind: str, effect_id: int, request: Request,
    file: UploadFile = File(...),
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    model = _model_for(kind)
    row = await session.get(model, effect_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    data = await file.read()
    if len(data) > _MAX_PREVIEW:
        raise HTTPException(status_code=413, detail="preview exceeds 30 MB")
    # Validate by CONTENT, never the client filename (a renamed non-media file must
    # not be stored and served). Video (mp4/webm) is kept as-is; an image is run
    # through the shared normalizer — JPEG/PNG/WEBP pass through, GIF/BMP/AVIF/TIFF
    # transcode to PNG, HEIC / non-media are rejected with a clear message.
    from api.images import _normalize_image

    vext = _detect_video_ext(data)
    if vext is not None:
        out_bytes, ext = data, vext
    else:
        norm = _normalize_image(data)
        if norm is None:
            raise HTTPException(
                status_code=400,
                detail="Не удалось обработать файл. Картинки: JPG, PNG, WEBP, GIF, BMP, "
                       "AVIF; видео: MP4, WEBM. Для HEIC (iPhone) сохраните как JPG.",
            )
        out_bytes, ext = norm

    os.makedirs(_MEDIA_DIR, exist_ok=True)
    fname = f"{kind}_{effect_id}_{uuid.uuid4().hex[:8]}{ext}"
    with open(os.path.join(_MEDIA_DIR, fname), "wb") as fh:
        fh.write(out_bytes)
    row.preview_url = f"/media/effects/{fname}"
    await audit(session, admin_id=admin.id, action="effect.preview", target_type=f"{kind}_effect",
    target_id=str(effect_id), after={"preview_url": row.preview_url}, ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return {"ok": True, "preview_url": row.preview_url}
