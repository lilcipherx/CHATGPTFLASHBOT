"""Public gallery Mini App endpoints (ТЗ §4).

Authenticates the same way as api.routers.miniapp — Telegram WebApp initData via
`current_webapp_user` (with the dev bypass on ENV=dev|test). Mounted under /api,
so routes resolve at /api/gallery and /api/gallery/submit."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import current_webapp_user
from core.db import get_session
from core.services import gallery
from core.services.gallery import ModerationRejected
from core.services.users import get_or_create_user

router = APIRouter(prefix="/gallery", tags=["gallery"])


class SubmitRequest(BaseModel):
    image_url: str
    prompt: str | None = None


def _card(item: gallery.GalleryItem) -> dict:
    return {
        "id": item.id,
        "image_url": item.image_url,
        "prompt": item.prompt,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.post("/submit")
async def submit_item(
    req: SubmitRequest,
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Submit one of the user's generated images to the public gallery for review."""
    user, _created = await get_or_create_user(
        session, tg["id"], tg.get("username"), tg.get("language_code")
    )
    if getattr(user, "is_banned", False):
        raise HTTPException(status_code=403, detail="banned")
    # FIX: AUDIT-P6 - rate-limit submissions. Without this a user could spam /submit,
    # burning one moderation call (an AI request per prompt) per hit and flooding the
    # review queue. 10/hour is well above any legitimate submission rate.
    from core.services import ratelimit
    if not await ratelimit.allow(f"gallery:submit:{user.user_id}", 10, 3600):
        raise HTTPException(status_code=429, detail="rate limit")
    image_url = (req.image_url or "").strip()
    if not image_url:
        raise HTTPException(status_code=400, detail="image_url required")
    # Only the app's own media (relative /media/...) or an http(s) URL. Reject
    # javascript:/data:/file:/other schemes so an approved item can never become a
    # content-injection sink for any consumer of the public gallery list.
    if not (image_url.startswith(("http://", "https://")) or image_url.startswith("/media/")):
        raise HTTPException(status_code=400, detail="invalid image url")
    # FIX: AUDIT-P6 - ownership check: a user may only submit an image THEY generated,
    # not an arbitrary URL or another user's result. Without this, one user could put
    # someone else's private result (or any internet image) into the public gallery under
    # their name. The legitimate source is the user's own History, whose entries are
    # GenerationJob.result_url rows for this user_id.
    from sqlalchemy import select as _select

    from core.models import GenerationJob
    owns = await session.scalar(
        _select(GenerationJob.job_id)
        .where(GenerationJob.user_id == user.user_id, GenerationJob.result_url == image_url)
        .limit(1)
    )
    if owns is None:
        raise HTTPException(status_code=403, detail="not your image")
    try:
        item = await gallery.submit(
            session, user.user_id, image_url, (req.prompt or "").strip() or None
        )
    except ModerationRejected as exc:
        raise HTTPException(status_code=400, detail="prompt blocked by moderation") from exc
    return {"id": item.id, "status": item.status}


@router.get("")
async def list_public(
    limit: int = 30,
    offset: int = 0,
    tg=Depends(current_webapp_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Public approved gallery, newest first (paginated)."""
    items = await gallery.public_list(session, limit, offset)
    return [_card(i) for i in items]
