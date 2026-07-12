"""Music generation worker — submit → poll → deliver audio, refund on failure."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

# FIX: AUDIT12-6..11 - structlog import for log.warning calls added by
# the AUDIT-11 pass (was: NameError on any worker error → worker crash).
import structlog

from core.ai_router.music_adapters import provider_for
from core.db import SessionFactory
from core.models import GenerationJob
from core.services.media_dispatch import resolve_backends, submit_or_resume
from core.services.refunds import refund_job

log = structlog.get_logger()

POLL_INTERVAL = 8
MAX_POLLS = 120


async def _refund_and_fail(session, job: GenerationJob, error: str) -> None:
    job.status = "failed"
    job.error = error
    job.completed_at = datetime.now(UTC)
    await refund_job(session, job)  # canonical 🪙/pack/free-slot reversal
    await session.commit()


async def _deliver(job: GenerationJob, url: str, locale: str) -> None:
    from core.bot_client import get_bot
    from core.i18n import t

    await get_bot().send_audio(job.user_id, url, caption=t("gen.song_ready", locale))


async def _deliver_and_finalise(job_id: str, result_url: str) -> None:
    """Idempotently deliver the finished song and mark the job complete. No-ops if
    already 'complete' (no double send); a delivery failure refunds + fails. The
    URL is already persisted by the caller, so a retry never re-submits/re-generates."""
    
    # FIX: B4 - CLAIM FIRST (conditional UPDATE), then deliver. The previous order
    # (deliver-then-claim) meant a stuck-job sweep that refunded the job during the slow
    # send_audio call left the user with BOTH the audio AND the refund, because the audio
    # was already sent before the conditional UPDATE checked status. Now: claim wins →
    # deliver → on delivery failure, flip back to failed+refund. Mirror video_tasks F16.
    from sqlalchemy import update as _update

    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status == "complete":
            return
        now = datetime.now(UTC)
        claim = await session.execute(
            _update(GenerationJob)
            .where(GenerationJob.job_id == job.job_id, GenerationJob.status == "processing")
            .values(status="complete", result_url=result_url, completed_at=now)
        )
        if claim.rowcount == 0:
            return  # sweep already finalised — do not double-deliver
        await session.commit()

    from core.services.users import user_locale

    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None:
            return
        locale = await user_locale(session, job.user_id)
        try:
            await _deliver(job, result_url, locale)
        except Exception as exc:  # noqa: BLE001 — delivery failed AFTER claim → refund
            await _refund_and_fail(session, job, f"deliver: {exc}")


async def process_music_job(ctx, job_id: str) -> None:
    # Phase A — claim + resume-or-submit (ARQ-retry idempotency: never re-submit or
    # re-generate when a prior attempt already produced a result / provider task).
    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status not in ("pending", "processing"):
            return
        if job.result_url:
            await _deliver_and_finalise(job_id, job.result_url)
            return
        backends = await resolve_backends(
            session, modality="music", model_key=job.service,
            params=job.params, direct_provider=provider_for(job.service),
        )
        backend, provider_job_id = await submit_or_resume(
            session, backends, existing_provider_job_id=job.provider_job_id,
            existing_backend=(job.params or {}).get("backend"),
        )
        if backend is None:
            await _refund_and_fail(session, job, "provider unavailable")
            return
        job.provider_job_id = provider_job_id
        # Persist the owning backend so an ARQ retry resumes polling the SAME
        # backend (a multi-backend pool must not poll a peer). Reassign params so
        # SQLAlchemy tracks the mutation.
        job.params = {**(job.params or {}), "backend": backend.name}
        # FIX: F5 - conditional UPDATE WHERE status IN ('pending','processing') AND
        # refunded_at IS NULL (same fix as F4 in video_tasks — prevents sweep from
        # racing the worker).
        # FIX: AUDIT-G3 - accept 'processing' too so a mid-flight redelivered job is
        # actually resumed (submit_or_resume reuses the provider task) instead of
        # rowcount 0 → silent return → stranded until the stuck sweep.
        from sqlalchemy import update as _update
        claim = await session.execute(
            _update(GenerationJob)
            .where(GenerationJob.job_id == job.job_id,
                   GenerationJob.status.in_(("pending", "processing")),
                   GenerationJob.refunded_at.is_(None))
            .values(status="processing", provider_job_id=provider_job_id,
                    params={**(job.params or {}), "backend": backend.name})
        )
        if claim.rowcount == 0:
            await session.rollback()
            return  # sweep already refunded — do not proceed
        await session.commit()

    # Phase B — poll outside the session.
    for _ in range(MAX_POLLS):
        await asyncio.sleep(POLL_INTERVAL)
        try:
            status = await backend.poll(provider_job_id)
        except Exception as exc:  # noqa: BLE001
            # FIX: AUDIT-11 - log poll failure
            log.warning("music.poll_failed", job_id=job_id, error=str(exc))
            continue
        if status.status == "complete" and status.result_url:
            # FIX: AI-11 - re-host the audio URL into OUR storage so History/Download
            # keep working after the Suno URL expires (Suno URLs live 1-24h). This
            # mirrors the video worker (video_tasks.py:203) which rehosts every
            # provider result. Best-effort: fall back to the provider URL on failure.
            from core.services import storage
            final_url = status.result_url
            try:
                rehosted = await storage.rehost_remote(status.result_url)
                if rehosted:
                    final_url = rehosted
            except Exception as exc:  # noqa: BLE001 — keep provider URL on failure
                log.warning("music.rehost_failed", job_id=job_id, error=str(exc))

            # Persist the URL BEFORE delivery so a retry resumes at delivery instead
            # of submitting/generating again.
            # FIX: SKILL-R1 - use a conditional UPDATE (WHERE status='processing')
            # instead of read-then-write. The old pattern was a TOCTOU race with the
            # stuck-job sweep: between the `if job.status != "processing"` check and
            # the `job.result_url = final_url; commit()`, the sweep could flip the
            # row to 'failed'+'refunded_at' — and we'd then overwrite result_url on
            # a refunded row, letting the user play audio after refund via
            # GET /api/jobs/{job_id}. The conditional UPDATE makes the claim atomic:
            # rowcount==0 means the sweep already refunded → skip delivery.
            from sqlalchemy import update as _upd
            async with SessionFactory() as session:
                claim = await session.execute(
                    _upd(GenerationJob)
                    .where(GenerationJob.job_id == job_id, GenerationJob.status == "processing")
                    .values(result_url=final_url)
                )
                if claim.rowcount == 0:
                    return  # sweep already refunded — do not deliver
                await session.commit()
            await _deliver_and_finalise(job_id, final_url)
            return
        if status.status == "failed":
            async with SessionFactory() as session:
                job = await session.get(GenerationJob, job_id)
                # Re-check status: the stuck-job sweep may have already failed +
                # refunded this job — refunding again would double-refund.
                if job is None or job.status != "processing":
                    return
                await _refund_and_fail(session, job, status.error or "provider failed")
            return

    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        # Same guard as the failure path against a concurrent sweep double-refund.
        if job is None or job.status != "processing":
            return
        await _refund_and_fail(session, job, "timeout")
