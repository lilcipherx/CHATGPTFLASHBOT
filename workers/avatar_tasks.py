"""Avatar generation worker (§3.1) — route through the media-gateway pool.

Mirrors workers/video_tasks.py: upload the selfie → resolve_backends(image) →
submit_or_resume → poll → collect ALL result URLs → deliver as Telegram albums →
refund the Stars purchase on genuine failure. When no gateway account is configured
the pool is empty, so the Stars purchase is refunded (previous stub behaviour)."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update

from core.db import SessionFactory
from core.models import GenerationJob
from core.queue import WORKER_QUEUE_NAME
from core.services.media_dispatch import resolve_backends, submit_or_resume
from core.services.refunds import refund_job

log = structlog.get_logger()

POLL_INTERVAL = 10       # seconds between polls
MAX_POLLS = 120          # ~20 min ceiling (avatar training is slow)
ALBUM_SIZE = 10          # Telegram media-group max


async def _notify_unavailable(user_id: int) -> None:
    from core.bot_client import get_bot
    from core.i18n import t
    from core.services.users import user_locale

    try:
        async with SessionFactory() as session:
            locale = await user_locale(session, user_id)
        await get_bot().send_message(user_id, t("gen.unavailable_refund", locale))
    except Exception as exc:  # noqa: BLE001
        log.warning("notify.unavailable_failed", user_id=user_id, error=str(exc))


async def _refund_and_fail(session, job: GenerationJob, error: str) -> None:
    job.status = "failed"
    job.error = error
    job.completed_at = datetime.now(UTC)
    await refund_job(session, job)  # avatar → refund_stars (money-first, idempotent)
    await session.commit()


async def _upload_file_id(file_id: str, job_id: str | None = None) -> str | None:
    if not file_id:
        return None
    try:
        if file_id.startswith(("http://", "https://")):
            return file_id
        from core.bot_client import get_bot
        from core.services import storage

        buf = await get_bot().download(file_id)
        return await storage.save_upload(buf.read(), "jpg", prefix="avatar-inputs")
    except Exception as exc:  # noqa: BLE001
        log.warning("avatar.selfie_upload_failed", job_id=job_id, error=str(exc))
        return None


async def _deliver_albums(user_id: int, urls: list[str]) -> int:
    """Send urls to chat in media groups of ALBUM_SIZE. Returns how many were sent.
    Best-effort per album so one bad group doesn't drop the rest."""
    from aiogram.types import InputMediaPhoto

    from core.bot_client import get_bot

    bot = get_bot()
    sent = 0
    for i in range(0, len(urls), ALBUM_SIZE):
        chunk = urls[i:i + ALBUM_SIZE]
        try:
            await bot.send_media_group(user_id, [InputMediaPhoto(media=u) for u in chunk])
            sent += len(chunk)
        except Exception as exc:  # noqa: BLE001 — a bad album must not drop the rest
            log.warning("avatar.album_send_failed", user_id=user_id, error=str(exc))
        await asyncio.sleep(1)  # ease Telegram rate limits between albums
    return sent


async def process_avatar_job(ctx, job_id: str) -> None:
    # Phase A — claim, upload selfie, submit.
    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status not in ("pending", "processing"):
            return
        row = job.params or {}
        selfie = row.get("selfie_file_id")
        count = int(row.get("count") or 1)
        if not selfie:
            await _refund_and_fail(session, job, "missing selfie")
            return
        url = await _upload_file_id(selfie, job_id)
        if not url:
            await _refund_and_fail(session, job, "selfie upload failed")
            return

        backends = await resolve_backends(
            session, modality="image", model_key="avatar",
            params={"image": url, "count": count}, direct_provider=None,
        )
        backend, provider_job_id = await submit_or_resume(
            session, backends, existing_provider_job_id=job.provider_job_id,
            existing_backend=row.get("backend"),
        )
        if backend is None:
            await _refund_and_fail(session, job, "avatar provider not configured")
            await _notify_unavailable(job.user_id)
            return

        claim = await session.execute(
            update(GenerationJob)
            .where(GenerationJob.job_id == job.job_id,
                   GenerationJob.status.in_(("pending", "processing")),
                   GenerationJob.refunded_at.is_(None))
            .values(status="processing", provider_job_id=provider_job_id,
                    params={**row, "backend": backend.name})
        )
        if claim.rowcount == 0:
            await session.rollback()
            return
        await session.commit()
        user_id = job.user_id

    # Phase B — poll outside the session.
    for _ in range(MAX_POLLS):
        await asyncio.sleep(POLL_INTERVAL)
        try:
            status = await backend.poll(provider_job_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("avatar.poll_failed", job_id=job_id, error=str(exc))
            continue
        if status.status == "complete":
            urls = list(status.result_urls) or (
                [status.result_url] if status.result_url else [])
            if not urls:
                async with SessionFactory() as session:
                    job = await session.get(GenerationJob, job_id)
                    if job is None or job.status != "processing":
                        return
                    await _refund_and_fail(session, job, "avatar: no results")
                return
            from core.services import storage

            final = [await storage.rehost_remote(u) or u for u in urls]
            async with SessionFactory() as session:
                job = await session.get(GenerationJob, job_id)
                if job is None or job.status != "processing":
                    return
                claim = await session.execute(
                    update(GenerationJob)
                    .where(GenerationJob.job_id == job_id, GenerationJob.status == "processing")
                    .values(status="complete", result_url=final[0],
                            completed_at=datetime.now(UTC))
                )
                if claim.rowcount == 0:
                    return
                await session.commit()
            delivered = await _deliver_albums(user_id, final)
            if delivered == 0:
                async with SessionFactory() as fail_session:
                    fail_job = await fail_session.get(GenerationJob, job_id)
                    if fail_job is not None and fail_job.status == "complete":
                        await _refund_and_fail(fail_session, fail_job, "avatar: delivery failed")
            return
        if status.status == "failed":
            async with SessionFactory() as session:
                job = await session.get(GenerationJob, job_id)
                if job is None or job.status != "processing":
                    return
                await _refund_and_fail(session, job, status.error or "provider failed")
            return

    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status != "processing":
            return
        await _refund_and_fail(session, job, "timeout")


async def claim_pending_avatars(ctx) -> int:
    """Cron sweep: enqueue any pending avatar jobs (e.g. after a restart) so a stuck
    purchase is processed (and, until a provider exists, refunded)."""
    async with SessionFactory() as session:
        rows = (
            await session.scalars(
                select(GenerationJob).where(
                    GenerationJob.service == "avatar",
                    GenerationJob.status == "pending",
                )
            )
        ).all()
        for job in rows:
            await ctx["redis"].enqueue_job(
                "process_avatar_job", str(job.job_id), _queue_name=WORKER_QUEUE_NAME
            )
        return len(rows)
