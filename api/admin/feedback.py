"""Admin: feedback dashboard (ТЗ §7) — 👍/👎 rating counts + open complaints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core.db import get_session
from core.models import AdminUser
from core.models.feedback import Complaint, MessageFeedback
from core.services import feedback

router = APIRouter(prefix="/feedback", tags=["admin-feedback"])


@router.get("/stats")
async def feedback_stats(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Aggregate counts: up, down, complaints_open."""
    return await feedback.stats(session)


@router.get("/complaints")
async def open_complaints(
    status: str = "open",   # open | resolved | all
    limit: int = 100,
    offset: int = 0,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Complaints, newest first, filtered by ``status`` (open | resolved | all).
    Bounded so the queue can never return an unbounded result set (mirrors the
    users-search pagination). The ``resolved`` flag is returned so the UI can badge
    each row."""
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    stmt = select(Complaint).order_by(Complaint.created_at.desc()).limit(limit).offset(offset)
    if status == "open":
        stmt = stmt.where(Complaint.resolved.is_(False))
    elif status == "resolved":
        stmt = stmt.where(Complaint.resolved.is_(True))
    # "all" → no status predicate
    rows = (await session.scalars(stmt)).all()
    return [
        {
            "id": c.id,
            "user_id": c.user_id,
            "content": c.content,
            "resolved": c.resolved,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in rows
    ]


@router.get("/ratings")
async def recent_ratings(
    rating: str = "down",   # down | up
    limit: int = 50,
    offset: int = 0,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Recent 👍/👎 votes with the rated-reply snippet, newest first — so the admin
    can SEE what users reacted to (esp. the disliked replies), not just the totals."""
    rating = "up" if rating == "up" else "down"
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    rows = (await session.scalars(
        select(MessageFeedback)
        .where(MessageFeedback.rating == rating)
        .order_by(MessageFeedback.created_at.desc())
        .limit(limit).offset(offset)
    )).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "rating": r.rating,
            "snippet": r.snippet,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/complaints/{complaint_id}/resolve")
async def resolve_complaint(
    complaint_id: int, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Mark a complaint resolved (clears it from the open list)."""
    if not await feedback.resolve_complaint(session, complaint_id):
        raise HTTPException(status_code=404, detail="not found")
    await audit(session, admin_id=admin.id, action="feedback.complaint.resolve",
                target_type="complaint", target_id=str(complaint_id),
                ip=request.client.host if request.client else None)
    return {"ok": True}
