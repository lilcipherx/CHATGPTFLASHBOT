"""Admin: channel autoposting (ТЗ §7).

An admin schedules a post to a Telegram channel; the workers.channel_tasks beat
cron publishes it when its time arrives. Every mutation is audited."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core.db import get_session
from core.models import AdminUser
from core.models.channel_post import ChannelPost
from core.services import channel_posts

router = APIRouter(prefix="/channel-posts", tags=["admin-channel"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


# FIX: M5 - validate the channel-post inline button URL before storing it. A channel
# post is published to EVERY subscriber, so a non-http(s)/tg scheme (javascript:,
# data:, vbscript:) on the button would be a stored-XSS vector across the whole
# audience. Mirror the same choke-point banners already enforce.
_BUTTON_URL_SCHEMES = ("http://", "https://", "tg://")


def _validate_button_url(url: str | None) -> str | None:
    link = (url or "").strip()
    if link and not link.lower().startswith(_BUTTON_URL_SCHEMES):
        raise HTTPException(
            status_code=400,
            detail="button_url must be an http(s) or tg:// URL",
        )
    return link or None


def _card(post: ChannelPost) -> dict:
    return {
        "id": post.id,
        "channel": post.channel,
        "text": post.text,
        "photo_url": post.photo_url,
        "button_text": post.button_text,
        "button_url": post.button_url,
        "status": post.status,
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "sent_at": post.sent_at.isoformat() if post.sent_at else None,
        "error": post.error,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
    }


class ChannelPostRequest(BaseModel):
    channel: str
    text: str = ""
    photo_url: str | None = None
    button_text: str | None = None
    button_url: str | None = None
    scheduled_at: str | None = None   # ISO datetime; None/past = next cron tick


@router.get("/")
async def list_posts(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = await channel_posts.list_recent(session, limit=50)
    return [_card(p) for p in rows]


@router.post("/")
async def create_post(
    req: ChannelPostRequest, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    channel = req.channel.strip()
    if not channel:
        raise HTTPException(status_code=400, detail="empty channel")
    if not req.text.strip() and not (req.photo_url or "").strip():
        raise HTTPException(status_code=400, detail="empty post (text or photo)")
    # FIX: M5 - reject an unsafe button scheme before the post is stored.
    button_url = _validate_button_url(req.button_url)
    run_at: datetime | None = None
    if req.scheduled_at:
        try:
            run_at = datetime.fromisoformat(req.scheduled_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="bad scheduled_at") from None
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=UTC)

    post = await channel_posts.create(
        session, channel=channel, text=req.text,
        photo_url=req.photo_url, button_text=req.button_text,
        button_url=button_url, scheduled_at=run_at,
    )
    await audit(session, admin_id=admin.id, action="channel_post.create",
                target_type="channel_post", target_id=str(post.id),
                after={"channel": channel, "scheduled": bool(run_at)}, ip=_ip(request))
    return _card(post)


@router.post("/{post_id}/send-now")
async def send_now(
    post_id: int, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Make a pending post due immediately (scheduled_at=now) so the next cron tick
    publishes it. Idempotent: only pending posts are touched."""
    post = await session.get(ChannelPost, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="not found")
    if post.status != "pending":
        raise HTTPException(status_code=400, detail="not pending")
    post.scheduled_at = datetime.now(UTC)
    await audit(session, admin_id=admin.id, action="channel_post.send_now",
    target_type="channel_post", target_id=str(post_id),
    ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return _card(post)


@router.delete("/{post_id}")
async def delete_post(
    post_id: int, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    post = await session.get(ChannelPost, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="not found")
    if post.status != "pending":
        raise HTTPException(status_code=400, detail="only pending can be deleted")
    await session.delete(post)
    await audit(session, admin_id=admin.id, action="channel_post.delete",
    target_type="channel_post", target_id=str(post_id), ip=_ip(request), commit=False)  # FIX: A1
    await session.commit()
    return {"ok": True}
