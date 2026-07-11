"""Avatar generation worker (§3.1 — async ~15 min, 100 images).

Picks up pending `generation_jobs` with service='avatar'. A real avatar provider
is not wired yet, so rather than leave the user charged with no result, the
worker REFUNDS the Telegram Stars purchase, fails the job and notifies the user.
When a provider key is available, replace the refund branch with the real
submit → poll → deliver pipeline (and only refund on genuine failure).
"""
from __future__ import annotations

from datetime import UTC, datetime

# FIX: AUDIT12-6..11 - structlog import for log.warning calls added by
# the AUDIT-11 pass (was: NameError on any worker error → worker crash).
import structlog
from sqlalchemy import select, update

from core.db import SessionFactory
from core.models import GenerationJob
from core.services.refunds import refund_stars

log = structlog.get_logger()


async def process_avatar_job(ctx, job_id: str) -> None:
    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status != "pending":
            return
        user_id = job.user_id
        # The exact Stars charge this job paid for (stored at selfie upload), so a user
        # with two avatar purchases refunds the RIGHT one — not just the newest.
        charge_id = (job.params or {}).get("charge_id")
        # FIX: AUDIT-G2 - atomic claim: conditional UPDATE WHERE status='pending' so a
        # duplicate ARQ enqueue (or the claim_pending_avatars sweep racing the original
        # dispatch) cannot both flip pending→processing and REFUND the SAME Stars
        # purchase twice. rowcount==0 → another worker already claimed it; bow out
        # silently. Matches the video/music/photoeffect claim pattern (was: plain
        # read-check-then-write, a TOCTOU race that double-refunded on concurrent runs).
        claim = await session.execute(
            update(GenerationJob)
            .where(GenerationJob.job_id == job_id, GenerationJob.status == "pending")
            .values(status="processing")
        )
        if claim.rowcount == 0:
            await session.rollback()
            return
        await session.commit()

        # No avatar provider configured yet → refund the Stars purchase so the user is
        # never charged for a product we cannot deliver. refund_stars issues the real
        # refund FIRST and marks the ledger only on success, so a transient bot failure
        # leaves the tx 'paid' (accurate / reconcilable) instead of a false 'refunded'.
        # FIX: AUDIT-11 - stub remains (no provider wired), log explicitly
        # TODO: when an avatar API key is available, call the provider here, deliver the
        log.warning("avatar.stub_no_provider", job_id=str(job.job_id), user_id=job.user_id)
        # 100 results, and only fall back to this refund branch on a genuine failure.
        from core.services.users import user_locale

        locale = await user_locale(session, user_id)
        refunded = await refund_stars(session, user_id, "avatar", charge_id, locale)
        job.status = "failed"
        job.error = (
            "avatar provider not configured — refunded" if refunded
            else "avatar provider not configured — refund pending (Stars not returned)"
        )
        job.completed_at = datetime.now(UTC)
        await session.commit()


async def claim_pending_avatars(ctx) -> int:
    """Cron sweep: enqueue any pending avatar jobs (e.g. after a restart) so a
    stuck purchase is processed (and, until a provider exists, refunded)."""
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
            await ctx["redis"].enqueue_job("process_avatar_job", str(job.job_id))
        return len(rows)
