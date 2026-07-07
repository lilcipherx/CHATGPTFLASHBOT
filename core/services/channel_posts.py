"""Channel-post service (ТЗ §7) — create/select/transition scheduled channel posts.

The worker (workers.channel_tasks) drives publishing; this module owns the row
lifecycle so both the admin API and the cron share one selection/transition path."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.channel_post import ChannelPost


async def create(
    session: AsyncSession,
    *,
    channel: str,
    text: str = "",
    photo_url: str | None = None,
    button_text: str | None = None,
    button_url: str | None = None,
    scheduled_at: datetime | None = None,
) -> ChannelPost:
    """Persist a pending channel post. scheduled_at None => publish on next tick."""
    post = ChannelPost(
        channel=channel,
        text=text or "",
        photo_url=(photo_url or "").strip() or None,
        button_text=(button_text or "").strip() or None,
        button_url=(button_url or "").strip() or None,
        scheduled_at=scheduled_at,
        status="pending",
    )
    session.add(post)
    await session.commit()
    return post


async def list_recent(session: AsyncSession, limit: int = 50) -> list[ChannelPost]:
    rows = await session.scalars(
        select(ChannelPost).order_by(ChannelPost.created_at.desc()).limit(limit)
    )
    return list(rows)


async def due(session: AsyncSession, now: datetime | None = None) -> list[ChannelPost]:
    """Pending posts whose time has come: scheduled_at in the past or unset."""
    now = now or datetime.now(UTC)
    rows = await session.scalars(
        select(ChannelPost).where(
            ChannelPost.status == "pending",
            (ChannelPost.scheduled_at.is_(None)) | (ChannelPost.scheduled_at <= now),
        )
    )
    return list(rows)


async def mark_sent(session: AsyncSession, post: ChannelPost) -> None:
    post.status = "sent"
    post.sent_at = datetime.now(UTC)
    post.error = None
    await session.commit()


async def mark_failed(session: AsyncSession, post: ChannelPost, error: str) -> None:
    post.status = "failed"
    post.error = error[:1000]
    await session.commit()
