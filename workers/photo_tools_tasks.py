"""Face Swap + Upscale workers (§15A).

Pipeline is complete (job → worker → refund-on-failure). The actual provider
call is a TODO — until a real face-swap / upscale API is wired, the worker
REFUNDS the credit and notifies the user instead of delivering the unprocessed
input as a fake result. Swap the `_process_*` bodies for the real provider call
(submit → deliver → mark complete) when keys arrive.
"""
from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import update

from core.db import SessionFactory
from core.models import GenerationJob
from core.services.refunds import refund_job

# FIX: AUDIT12-6..11 - structlog logger for log.warning calls added by the AUDIT-11
# pass (was: NameError on any worker error → worker crash).
log = structlog.get_logger()


async def _notify_unavailable(user_id: int) -> None:
    """Tell the user the tool is temporarily unavailable and the credit was
    returned. Best-effort — never raises."""
    from core.bot_client import get_bot
    from core.db import SessionFactory
    from core.i18n import t
    from core.services.users import user_locale

    try:
        async with SessionFactory() as session:
            locale = await user_locale(session, user_id)
        await get_bot().send_message(user_id, t("gen.unavailable_refund", locale))
    except Exception as exc:  # noqa: BLE001
        # FIX: AUDIT-11 - log instead of silent pass
        log.warning("notify.unavailable_failed", user_id=user_id, error=str(exc))


async def _refund_and_fail(session, job: GenerationJob, error: str) -> None:
    job.status = "failed"
    job.error = error
    job.completed_at = datetime.now(UTC)
    # Canonical reversal — handles credits / image-video-music packs / free slots,
    # not just the image pack (a faceswap/upscale job charged in 🪙 credits would
    # otherwise raise in packs.refund and never be refunded).
    await refund_job(session, job)
    await session.commit()


async def process_faceswap_job(ctx, job_id: str) -> None:
    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status != "pending":
            return
        # FIX: AUDIT-G5 - atomic claim (conditional UPDATE WHERE status='pending'),
        # matching video/music/photoeffect/avatar. rowcount==0 → another worker
        # already claimed this job, so bow out instead of refunding it a second time.
        claim = await session.execute(
            update(GenerationJob)
            .where(GenerationJob.job_id == job_id, GenerationJob.status == "pending")
            .values(status="processing")
        )
        if claim.rowcount == 0:
            await session.rollback()
            return
        await session.commit()
        src = (job.params or {}).get("source")
        if not src:
            await _refund_and_fail(session, job, "missing source photo")
            return
        # No real face-swap provider is wired yet. Refund the credit instead of
        # delivering the unprocessed input as if it were a result. When a provider
        # is connected, replace this with submit → deliver → mark complete (and
        # only refund on a genuine failure).
        # FIX: AUDIT-11 - log stub explicitly
        log.warning("faceswap.stub_no_provider", job_id=str(job.job_id), user_id=job.user_id)
        await _refund_and_fail(session, job, "faceswap provider not configured")

        await _notify_unavailable(job.user_id)


async def process_upscale_job(ctx, job_id: str) -> None:
    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status != "pending":
            return
        # FIX: AUDIT-G5 - atomic claim (conditional UPDATE WHERE status='pending'),
        # matching video/music/photoeffect/avatar. rowcount==0 → another worker
        # already claimed this job, so bow out instead of refunding it a second time.
        claim = await session.execute(
            update(GenerationJob)
            .where(GenerationJob.job_id == job_id, GenerationJob.status == "pending")
            .values(status="processing")
        )
        if claim.rowcount == 0:
            await session.rollback()
            return
        await session.commit()
        img = (job.params or {}).get("image")
        if not img:
            await _refund_and_fail(session, job, "missing image")
            return
        # No real upscaler provider (Real-ESRGAN/etc.) is wired yet. Refund the
        # credits rather than delivering the untouched input as a "result". Wire
        # the real provider here when available (deliver → complete; refund only
        # on a genuine failure).
        # FIX: AUDIT-11 - log stub explicitly
        log.warning("upscale.stub_no_provider", job_id=str(job.job_id), user_id=job.user_id)
        await _refund_and_fail(session, job, "upscale provider not configured")

        await _notify_unavailable(job.user_id)
