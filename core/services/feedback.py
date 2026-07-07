"""Feedback service (ТЗ §7): record 👍/👎 ratings + complaints, and aggregate
counts for the admin panel."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.feedback import Complaint, MessageFeedback


async def record_rating(
    session: AsyncSession, user_id: int, rating: str, snippet: str | None
) -> MessageFeedback:
    """Store a 👍/👎 vote. ``rating`` is "up" or "down"; snippet is trimmed to 200 chars."""
    if rating not in ("up", "down"):
        raise ValueError(f"invalid rating {rating!r}")
    fb = MessageFeedback(
        user_id=user_id, rating=rating, snippet=(snippet or None) and snippet[:200]
    )
    session.add(fb)
    await session.commit()
    return fb


async def record_complaint(session: AsyncSession, user_id: int, content: str) -> Complaint:
    """Store a free-text complaint (open by default)."""
    c = Complaint(user_id=user_id, content=content)
    session.add(c)
    await session.commit()
    return c


async def resolve_complaint(session: AsyncSession, complaint_id: int) -> bool:
    """Mark a complaint resolved. Returns False if it doesn't exist (already gone)."""
    c = await session.get(Complaint, complaint_id)
    if c is None:
        return False
    c.resolved = True
    await session.commit()
    return True


async def stats(session: AsyncSession) -> dict:
    """Aggregate counts for the admin dashboard."""
    up = await session.scalar(
        select(func.count()).select_from(MessageFeedback)
        .where(MessageFeedback.rating == "up")
    )
    down = await session.scalar(
        select(func.count()).select_from(MessageFeedback)
        .where(MessageFeedback.rating == "down")
    )
    complaints_open = await session.scalar(
        select(func.count()).select_from(Complaint).where(Complaint.resolved.is_(False))
    )
    return {
        "up": int(up or 0),
        "down": int(down or 0),
        "complaints_open": int(complaints_open or 0),
    }
