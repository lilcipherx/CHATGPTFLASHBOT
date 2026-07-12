"""Admin: Mini App carousel banners (CRUD + image upload) and the single global
rotation-interval setting. The interval lives in the `pricing` KV table under
key ``miniapp_carousel`` so it is runtime-editable with no redeploy. All
mutations are audited; moderators can edit, admins can delete."""
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from api.carousel import _sanitize_behavior
from core.db import get_session
from core.models import AdminUser, MiniAppBanner, Pricing

router = APIRouter(prefix="/banners", tags=["admin-banners"])

_MEDIA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "media", "banners")
_MAX = 30 * 1024 * 1024

CAROUSEL_KEY = "miniapp_carousel"
DEFAULT_INTERVAL_MS = 5000
MIN_INTERVAL_MS = 1500
MAX_INTERVAL_MS = 60000


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _validate_link_url(url: str | None) -> str | None:
    """A carousel banner's link_url is rendered as a clickable href in the Mini App
    home screen shown to EVERY user, so a non-http(s) scheme (javascript:, data:,
    vbscript:) would be a stored-XSS vector against the whole user base. Allow only
    empty or an http(s) URL; reject anything else at this single choke point rather
    than relying on each render site to sanitize."""
    link = (url or "").strip()
    if link and not link.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="link_url must be an http(s) URL")
    return link or None


def _norm_locale(value: str | None) -> str | None:
    """Normalize an admin-entered locale to a supported 2-letter code, or None
    (= shown to every language). Anything blank/'all'/unknown becomes None."""
    from core.constants import SUPPORTED_LOCALES

    code = (value or "").strip().lower()
    return code if code in SUPPORTED_LOCALES else None


def _dict(b: MiniAppBanner) -> dict:
    return {
        "id": b.id,
        "image_url": b.image_url,
        "title": b.title,
        "subtitle": b.subtitle,
        "link_url": b.link_url,
        "locale": b.locale,
        "sort_order": b.sort_order,
        "enabled": b.enabled,
        "impressions": b.impressions or 0,
        "clicks": b.clicks or 0,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


async def _get_settings(session: AsyncSession) -> tuple[int, dict]:
    row = await session.get(Pricing, CAROUSEL_KEY)
    val = (row.value or {}) if row else {}
    try:
        ms = int(val.get("interval_ms", DEFAULT_INTERVAL_MS))
    except (TypeError, ValueError):
        ms = DEFAULT_INTERVAL_MS
    ms = max(MIN_INTERVAL_MS, min(MAX_INTERVAL_MS, ms))
    return ms, _sanitize_behavior(val.get("behavior"))


@router.get("")
async def list_banners(
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rows = (await session.scalars(
        select(MiniAppBanner).order_by(MiniAppBanner.sort_order, MiniAppBanner.id)
    )).all()
    interval_ms, behavior = await _get_settings(session)
    return {"interval_ms": interval_ms, "behavior": behavior, "banners": [_dict(b) for b in rows]}


class BannerUpsert(BaseModel):
    # FIX: AUDIT13-M10 - bound storefront strings shown to every Mini App user.
    image_url: str = Field("", max_length=2048)
    title: str | None = Field(None, max_length=200)
    subtitle: str | None = Field(None, max_length=500)
    link_url: str | None = Field(None, max_length=2048)
    locale: str | None = Field(None, max_length=8)      # None/'' = shown to all languages
    sort_order: int = 0
    enabled: bool = True


@router.post("")
async def create_banner(
    req: BannerUpsert, request: Request,
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = MiniAppBanner(
        image_url=req.image_url, title=req.title, subtitle=req.subtitle,
        link_url=_validate_link_url(req.link_url), locale=_norm_locale(req.locale),
        sort_order=req.sort_order, enabled=req.enabled,
    )
    session.add(row)
    await audit(session, admin_id=admin.id, action="banner.create", target_type="banner",
                # FIX: A1
                target_id=str(row.id), after={"title": req.title}, ip=_ip(request), commit=False)
    await session.commit()
    return _dict(row)


@router.put("/{banner_id}")
async def update_banner(
    banner_id: int, req: BannerUpsert, request: Request,
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await session.get(MiniAppBanner, banner_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    # image_url is only overwritten when a non-empty value is sent, so saving the
    # row after a separate image upload does not wipe the uploaded URL.
    if req.image_url:
        row.image_url = req.image_url
    row.title = req.title
    row.subtitle = req.subtitle
    row.link_url = _validate_link_url(req.link_url)
    row.locale = _norm_locale(req.locale)
    row.sort_order = req.sort_order
    row.enabled = req.enabled
    await audit(session, admin_id=admin.id, action="banner.update", target_type="banner",
    # FIX: A1
    target_id=str(banner_id), after={"enabled": req.enabled}, ip=_ip(request), commit=False)
    await session.commit()
    return _dict(row)


@router.delete("/{banner_id}")
async def delete_banner(
    banner_id: int, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await session.get(MiniAppBanner, banner_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    await session.delete(row)
    await audit(session, admin_id=admin.id, action="banner.delete", target_type="banner",
    target_id=str(banner_id), ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return {"ok": True}


@router.post("/{banner_id}/image")
async def upload_image(
    banner_id: int, request: Request,
    file: UploadFile = File(...),
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await session.get(MiniAppBanner, banner_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    data = await file.read()
    if len(data) > _MAX:
        raise HTTPException(status_code=413, detail="image exceeds 30 MB")
    # Validate + normalize by CONTENT (magic bytes / Pillow decode), never the client
    # filename. JPEG/PNG/WEBP are stored as-is; other decodable formats (GIF, BMP,
    # AVIF, TIFF…) are transcoded to PNG so the slide always renders. HEIC (iPhone)
    # and non-images can't be decoded → a clear 400 instead of a stored dead file.
    from api.images import _normalize_image

    norm = _normalize_image(data)
    if norm is None:
        raise HTTPException(
            status_code=400,
            detail="Не удалось обработать изображение. Поддерживаются JPG, PNG, WEBP, "
                   "GIF, BMP, AVIF. Для HEIC (фото с iPhone) сначала сохраните как JPG.",
        )
    out_bytes, ext = norm
    os.makedirs(_MEDIA_DIR, exist_ok=True)
    fname = f"banner_{banner_id}_{uuid.uuid4().hex[:8]}{ext}"
    with open(os.path.join(_MEDIA_DIR, fname), "wb") as fh:
        fh.write(out_bytes)
    row.image_url = f"/media/banners/{fname}"
    await audit(session, admin_id=admin.id, action="banner.image", target_type="banner",
    # FIX: A1
    target_id=str(banner_id), after={"image_url": row.image_url}, ip=_ip(request), commit=False)
    await session.commit()
    return {"ok": True, "image_url": row.image_url}


class CarouselSettingsReq(BaseModel):
    interval_ms: int
    behavior: dict = {}


@router.put("/settings")
async def set_settings(
    req: CarouselSettingsReq, request: Request,
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Persist the carousel interval + render behaviour into the miniapp_carousel
    KV value. interval_ms stays where the Mini App reads it; behaviour is nested."""
    ms = max(MIN_INTERVAL_MS, min(MAX_INTERVAL_MS, int(req.interval_ms)))
    beh = _sanitize_behavior(req.behavior)
    row = await session.get(Pricing, CAROUSEL_KEY)
    value = dict(row.value or {}) if row else {}
    value["interval_ms"] = ms
    value["behavior"] = beh
    if row is None:
        session.add(Pricing(key=CAROUSEL_KEY, value=value))
    else:
        row.value = value
    # FIX: A1
    await audit(session, admin_id=admin.id, action="banner.settings", target_type="setting",
                target_id=CAROUSEL_KEY, after={"interval_ms": ms, "behavior": beh},
                ip=_ip(request), commit=False)
    await session.commit()
    return {"interval_ms": ms, "behavior": beh}


class IntervalReq(BaseModel):
    interval_ms: int


@router.put("/settings/interval")
async def set_interval(
    req: IntervalReq, request: Request,
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    ms = max(MIN_INTERVAL_MS, min(MAX_INTERVAL_MS, int(req.interval_ms)))
    row = await session.get(Pricing, CAROUSEL_KEY)
    value = dict(row.value or {}) if row else {}
    value["interval_ms"] = ms
    if row is None:
        session.add(Pricing(key=CAROUSEL_KEY, value=value))
    else:
        row.value = value
    await audit(session, admin_id=admin.id, action="banner.interval", target_type="setting",
    target_id=CAROUSEL_KEY, after={"interval_ms": ms}, ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return {"interval_ms": ms}
