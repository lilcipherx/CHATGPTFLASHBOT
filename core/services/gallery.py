"""Public gallery service (ТЗ §4): submit + moderation + public listing.

A submitted item starts `pending`; a moderator flips it to `approved` / `rejected`.
Only approved items are visible to the public. Submitting a prompt that fails
content moderation is rejected up front (parity with the bot/Mini App rules)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.gallery import GalleryItem
from core.services import moderation

# Valid moderation states a moderator may set an item to.
VALID_STATUSES = ("approved", "rejected", "pending")


class ModerationRejected(Exception):
    """A submission's prompt was blocked by content moderation."""

    def __init__(self, reason: str | None = None) -> None:
        super().__init__(reason or "prompt blocked by moderation")
        self.reason = reason


async def submit(
    session: AsyncSession,
    user_id: int,
    image_url: str,
    prompt: str | None = None,
) -> GalleryItem:
    """Create a pending gallery item for `user_id`. If a prompt is supplied it is
    content-moderated first; a disallowed prompt raises ModerationRejected and no
    item is created."""
    if prompt:
        result = await moderation.moderate(prompt)
        if not result.allowed:
            raise ModerationRejected(result.reason)
    item = GalleryItem(
        user_id=user_id,
        image_url=image_url,
        prompt=prompt,
        status="pending",
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def public_list(
    session: AsyncSession, limit: int = 30, offset: int = 0
) -> list[GalleryItem]:
    """Approved items only, newest first (paginated)."""
    limit = max(1, min(100, limit))
    offset = max(0, offset)
    rows = await session.scalars(
        select(GalleryItem)
        .where(GalleryItem.status == "approved")
        .order_by(GalleryItem.created_at.desc(), GalleryItem.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.all())


async def pending_list(session: AsyncSession) -> list[GalleryItem]:
    """The moderation queue: pending items, oldest first."""
    rows = await session.scalars(
        select(GalleryItem)
        .where(GalleryItem.status == "pending")
        .order_by(GalleryItem.created_at.asc(), GalleryItem.id.asc())
    )
    return list(rows.all())


async def list_by_status(
    session: AsyncSession, status: str, limit: int = 100, offset: int = 0
) -> list[GalleryItem]:
    """Items in a given moderation state, for the admin queue/history views. Pending
    is oldest-first (FIFO review); approved/rejected are newest-first (recent history)."""
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    limit = max(1, min(200, limit))
    offset = max(0, offset)
    order = (
        (GalleryItem.created_at.asc(), GalleryItem.id.asc())
        if status == "pending"
        else (GalleryItem.created_at.desc(), GalleryItem.id.desc())
    )
    rows = await session.scalars(
        select(GalleryItem)
        .where(GalleryItem.status == status)
        .order_by(*order)
        .limit(limit)
        .offset(offset)
    )
    return list(rows.all())


async def set_status(
    session: AsyncSession, item_id: int, status: str, admin_id: int
) -> GalleryItem | None:
    """Flip an item's moderation status, recording who moderated it. Returns the
    updated item, or None if it doesn't exist. Raises ValueError on a bad status."""
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {status}")
    item = await session.get(GalleryItem, item_id)
    if item is None:
        return None
    item.status = status
    item.moderated_by = admin_id
    await session.commit()
    await session.refresh(item)
    return item
