"""Result retention (ТЗ §5 «срок хранения результатов»).

An admin sets how many days generated artifacts are kept; a daily cron
(workers.retention_tasks) calls run_retention to DELETE rows past the window.
0 days = keep forever (skip the prune). Windows come from pricing.retention().
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import CheckoutIntent, GalleryItem, GenerationJob
from core.services import pricing, storage

# Abandoned-cart intents are tiny and only ever read within their reminder window, so
# a fixed retention keeps the table bounded without another admin knob.
_INTENT_RETENTION_DAYS = 30

# Jobs in a non-terminal state are still in flight (or queued) and must never be
# pruned — only complete/failed jobs are finished artifacts safe to drop. NOTE: the
# success status the workers write is "complete" (not "completed") — using the wrong
# spelling silently pruned nothing but failed jobs, letting the table grow forever.
_TERMINAL = ("complete", "failed")


async def _drop_storage(urls: list[str | None]) -> None:
    """Best-effort delete of OUR stored objects referenced by pruned rows, so the DB
    prune doesn't orphan files. `storage.delete` only touches our own URLs (local /media
    + S3 public-URL); provider/presigned URLs are skipped. Runs AFTER the DB commit so a
    storage hiccup never blocks the prune."""
    for url in urls:
        if url:
            await storage.delete(url)


async def prune_jobs(session: AsyncSession, job_days: int) -> int:
    """DELETE terminal (completed/failed) GenerationJob rows older than job_days, and
    drop their re-hosted media from storage. Pending/processing jobs are left untouched
    (still in flight). Telegram file_ids need no cleanup. Returns the rows deleted.
    """
    if job_days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=job_days)
    urls = list(await session.scalars(
        select(GenerationJob.result_url).where(
            GenerationJob.status.in_(_TERMINAL),
            GenerationJob.created_at < cutoff,
            GenerationJob.result_url.is_not(None),
        )
    ))
    res = await session.execute(
        delete(GenerationJob).where(
            GenerationJob.status.in_(_TERMINAL),
            GenerationJob.created_at < cutoff,
        )
    )
    await session.commit()
    await _drop_storage(urls)
    return res.rowcount or 0


async def prune_gallery(session: AsyncSession, gallery_days: int) -> int:
    """DELETE GalleryItem rows older than gallery_days + drop their images from storage.
    Returns count."""
    if gallery_days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=gallery_days)
    urls = list(await session.scalars(
        select(GalleryItem.image_url).where(GalleryItem.created_at < cutoff)
    ))
    res = await session.execute(
        delete(GalleryItem).where(GalleryItem.created_at < cutoff)
    )
    await session.commit()
    await _drop_storage(urls)
    return res.rowcount or 0


async def prune_checkout_intents(session: AsyncSession, days: int = _INTENT_RETENTION_DAYS) -> int:
    """DELETE abandoned-cart intents older than ``days`` (any state — a cart this old is
    long past its reminder window). Keeps checkout_intents bounded. Returns count."""
    if days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=days)
    res = await session.execute(
        delete(CheckoutIntent).where(CheckoutIntent.created_at < cutoff)
    )
    await session.commit()
    return res.rowcount or 0


async def run_retention(session: AsyncSession | None = None) -> dict[str, int]:
    """Read the admin-configured windows and prune both job + gallery artifacts.

    Skips a prune whose window is 0 (keep forever). Opens its own session when
    none is supplied (the cron path). Returns {jobs_pruned, gallery_pruned, intents_pruned}.
    """
    if session is None:
        from core.db import SessionFactory

        async with SessionFactory() as own:
            return await run_retention(own)

    cfg = await pricing.retention(session)
    return {
        "jobs_pruned": await prune_jobs(session, cfg["job_days"]),
        "gallery_pruned": await prune_gallery(session, cfg["gallery_days"]),
        "intents_pruned": await prune_checkout_intents(session),
    }
