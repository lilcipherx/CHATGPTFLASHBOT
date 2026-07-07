"""Admin: public-gallery moderation (ТЗ §4).

A moderator sees the pending submission queue and approves / rejects each item;
every decision is audited."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core.db import get_session
from core.models import AdminUser
from core.models.gallery import GalleryItem  # FIX: AUDIT-FINAL-5 - NameError on /approve
from core.services import gallery

router = APIRouter(prefix="/gallery", tags=["admin-gallery"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _card(item: gallery.GalleryItem) -> dict:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "image_url": item.image_url,
        "prompt": item.prompt,
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.get("/pending")
async def pending(
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """The moderation queue: items awaiting review, oldest first."""
    rows = await gallery.pending_list(session)
    return [_card(r) for r in rows]


@router.get("/list")
async def list_items(
    status: str = "pending",   # pending | approved | rejected
    limit: int = 100,
    offset: int = 0,
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Items by moderation status — powers the queue (pending) AND the history tabs
    (approved / rejected). Unknown status falls back to pending."""
    if status not in gallery.VALID_STATUSES:
        status = "pending"
    rows = await gallery.list_by_status(session, status, limit=limit, offset=offset)
    return [_card(r) for r in rows]


async def _moderate(
    item_id: int, status: str, admin: AdminUser, request: Request, session: AsyncSession
) -> dict:
    item = await gallery.set_status(session, item_id, status, admin.id)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    await audit(
        session, admin_id=admin.id, action=f"gallery.{status}",
        target_type="gallery_item", target_id=str(item_id),
        after={"status": status}, ip=_ip(request),
    )
    return {"ok": True, "id": item.id, "status": item.status}


@router.post("/{item_id}/approve")
async def approve_item(
    item_id: int,
    request: Request,
    admin: AdminUser = Depends(require_role("moderator", "admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Approve a pending submission. Re-hosts external image URLs server-side so
    viewers never leak their IP to a third-party host."""
    item = await session.get(GalleryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="not found")
    # FIX: AUDIT-25 - re-host external image URLs server-side (privacy: no IP leak)
    if item.image_url and item.image_url.startswith(("http://", "https://")):
        try:
            from core.services.storage import rehost_remote
            new_url = await rehost_remote(item.image_url, prefix="gallery")
            if new_url:
                item.image_url = new_url
        except Exception:
            pass  # best-effort; keep original URL if re-host fails
    item.status = "approved"
    item.moderated_by = admin.id
    # FIX: AUDIT-TEST - record the moderation action (parity with reject/_moderate);
    # approvals were previously NOT written to the audit log.
    await audit(
        session, admin_id=admin.id, action="gallery.approved",
        target_type="gallery_item", target_id=str(item_id),
        after={"status": "approved"}, ip=_ip(request), commit=False,
    )
    await session.commit()
    return {"ok": True, "status": "approved"}


@router.post("/{item_id}/reject")
async def reject(
    item_id: int,
    request: Request,
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await _moderate(item_id, "rejected", admin, request, session)
