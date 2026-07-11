"""Admin: «Требует внимания» — counts of items needing operator action (ТЗ §8).

A single cheap COUNT per category that the dashboard surfaces near the top:
stuck generation jobs, open complaints, the gallery moderation queue, the open
support inbox, and failed channel posts. Each COUNT is wrapped in its own
try/except returning 0 so a missing/renamed table can never 500 the whole panel.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.deps import require_role
from core.config import settings
from core.db import get_session
from core.models import (
    AdminUser,
    ChannelPost,
    Complaint,
    GalleryItem,
    GenerationJob,
    SupportMessage,
)

_log = structlog.get_logger()

router = APIRouter(prefix="/attention", tags=["admin-attention"])


async def _count(session: AsyncSession, stmt) -> int:
    """Run a COUNT, returning 0 on any failure (e.g. a missing table) so one
    broken category can never take down the whole attention panel."""
    try:
        return int(await session.scalar(stmt) or 0)
    except Exception as exc:  # noqa: BLE001 — FIX: F38 - log so a broken category
        # is observable (was bare `return 0`; operators couldn't tell why a count
        # was permanently 0). Still best-effort: the panel renders 0 for this category.
        _log.warning("attention.count_failed", error=str(exc))
        return 0


@router.get("/")
async def attention(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # "Stuck" mirrors the worker sweep: pending/processing older than the threshold.
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.stuck_job_minutes)

    stuck_jobs = await _count(
        session,
        select(func.count())
        .select_from(GenerationJob)
        .where(
            GenerationJob.status.in_(("pending", "processing")),
            GenerationJob.created_at < cutoff,
        ),
    )
    open_complaints = await _count(
        session,
        select(func.count()).select_from(Complaint).where(Complaint.resolved.is_(False)),
    )
    pending_gallery = await _count(
        session,
        select(func.count()).select_from(GalleryItem).where(GalleryItem.status == "pending"),
    )
    open_support = await _count(
        session,
        select(func.count())
        .select_from(SupportMessage)
        .where(SupportMessage.direction == "in", SupportMessage.handled.is_(False)),
    )
    failed_channel_posts = await _count(
        session,
        select(func.count()).select_from(ChannelPost).where(ChannelPost.status == "failed"),
    )

    total = (
        stuck_jobs + open_complaints + pending_gallery + open_support + failed_channel_posts
    )
    return {
        "stuck_jobs": stuck_jobs,
        "open_complaints": open_complaints,
        "pending_gallery": pending_gallery,
        "open_support": open_support,
        "failed_channel_posts": failed_channel_posts,
        "total": total,
    }
