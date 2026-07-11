"""Video generation worker — submit → poll → deliver, refund on failure.

Drives any generation_job with pack_type='video' (config services + Kling
Effects/Motion) through its provider adapter and delivers the result to the user
via the bot. On failure the video credits are returned."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

# FIX: AUDIT12-6..11 - structlog import for log.warning calls added by
# the AUDIT-11 pass (was: NameError on any worker error → worker crash).
import structlog

from core.ai_router.video_adapters import provider_for
from core.db import SessionFactory
from core.models import GenerationJob
from core.services.media_dispatch import resolve_backends, submit_or_resume
from core.services.refunds import refund_job

log = structlog.get_logger()

POLL_INTERVAL = 8       # seconds between polls
MAX_POLLS = 150         # ~20 min ceiling


async def _refund_and_fail(session, job: GenerationJob, error: str) -> None:
    job.status = "failed"
    job.error = error
    job.completed_at = datetime.now(UTC)
    await refund_job(session, job)  # canonical 🪙/pack/free-slot reversal
    await session.commit()


async def _deliver(job: GenerationJob, result_url: str, locale: str) -> None:
    from core.bot_client import get_bot
    from core.i18n import t

    await get_bot().send_video(
        job.user_id, result_url, caption=t("gen.video_ready", locale)
    )


async def _deliver_and_finalise(job_id: str, result_url: str) -> None:
    """Idempotently deliver the finished video and mark the job complete.

    Delivery is ORIGIN-AWARE, because this worker is shared by the bot and the Mini
    App:
      * Mini App video EFFECTS (params carry a ``preset_id``) have an in-app result
        screen + History, so the IN-APP channel is primary: mark complete + persist
        the URL FIRST, then push to chat best-effort. A chat-send failure (provider
        URL not Telegram-fetchable, file over the bot limit, bot blocked) must NOT
        discard an already generated+paid video or refund it — parity with the
        photo-effect worker, whose in-app History is likewise the primary channel.
      * Bot video generations have NO in-app fallback — the chat IS the delivery, so
        a send failure refunds + fails (never charge for a video never received).

    Safe to call again on an ARQ retry: a 'complete' job no-ops (no double send). The
    result URL is already persisted by the caller, so a crash here never triggers a
    re-submit/re-generate — at worst an existing URL is re-sent (free)."""
    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status == "complete":
            return  # already delivered & finalised
        from sqlalchemy import update as _update

        from core.services.users import user_locale

        locale = await user_locale(session, job.user_id)
        # A Mini App generation is in-app when it carries a preset_id (curated effect)
        # OR a free_model marker (free-choice model path, § variant 3).
        p = job.params or {}
        in_app = p.get("preset_id") is not None or bool(p.get("free_model"))

        if in_app:
            # In-app primary: finalise FIRST so the Mini App always shows the result,
            # then attempt the bonus chat delivery without risking the paid result.
            # FIX: R20 - conditional UPDATE WHERE status='processing' so two ARQ retries
            # (or a retry racing the stuck-job sweep) can't both flip the same row to
            # 'complete' and double-deliver the chat message. rowcount==0 means another
            # attempt already finalised — return silently.
            now = datetime.now(UTC)
            claim = await session.execute(
                _update(GenerationJob)
                .where(GenerationJob.job_id == job.job_id, GenerationJob.status == "processing")
                .values(status="complete", result_url=result_url, completed_at=now)
            )
            if claim.rowcount == 0:
                return  # another attempt already finalised
            await session.commit()
            try:
                await _deliver(job, result_url, locale)
            except Exception:  # noqa: BLE001 — chat is a bonus channel for effects
                pass
            return

        # Bot generation: chat is the only channel — a send failure refunds + fails.
        # FIX: F16 - CLAIM FIRST (conditional UPDATE), then deliver. The previous order
        # (deliver-then-claim) meant a stuck-job sweep that refunded the job during the
        # slow send_video call left the user with BOTH the video AND the refund, because
        # the video was already sent before the conditional UPDATE checked status.
        # Now: claim wins → deliver → on delivery failure, flip back to failed+refund.
        now = datetime.now(UTC)
        claim = await session.execute(
            _update(GenerationJob)
            .where(GenerationJob.job_id == job.job_id, GenerationJob.status == "processing")
            .values(status="complete", result_url=result_url, completed_at=now)
        )
        if claim.rowcount == 0:
            return  # another attempt / sweep already finalised
        await session.commit()
        try:
            await _deliver(job, result_url, locale)
        except Exception as exc:  # noqa: BLE001 — delivery failed AFTER claim → refund
            # Re-open a session to flip the just-claimed 'complete' back to 'failed' +
            # refund, so the user isn't left marked complete with no delivered video.
            async with SessionFactory() as fail_session:
                fail_job = await fail_session.get(GenerationJob, job_id)
                if fail_job is not None and fail_job.status == "complete":
                    await _refund_and_fail(fail_session, fail_job, f"deliver: {exc}")
            return


async def process_video_job(ctx, job_id: str) -> None:
    # Phase A — claim the job and either RESUME a prior provider task or submit a
    # new one. Never re-submit/re-generate when a previous attempt already produced
    # a result or already has a provider task (ARQ-retry idempotency).
    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status not in ("pending", "processing"):
            return
        if job.result_url:
            # A previous attempt already generated the video — skip straight to
            # idempotent delivery; do NOT submit or generate again.
            await _deliver_and_finalise(job_id, job.result_url)
            return
        # FIX: F2 - if the job has an image_file_id (Telegram file ID), download it,
        # upload to our storage, and inject image_url into params so the provider
        # receives a publicly-fetchable URL for image2video. Without this, has_image
        # is always False and every Kling image2video silently degrades to text2video.
        # FIX: AI-16 - unified image lookup. The bot path uses `image_file_id`, the
        # Mini App path uses `input_images` (list of file_ids or URLs), and the old
        # Kling Effects path used `photo_file_id` (now migrated to image_file_id by
        # AI-8). Pick the FIRST usable image source so all three paths feed Kling's
        # image2video endpoint correctly.
        params = dict(job.params or {})
        if not params.get("image_url"):
            # Collect candidate image sources in priority order.
            image_file_id = params.get("image_file_id") or params.get("photo_file_id")
            input_images = params.get("input_images") or []
            # Mini App sends input_images as a list of {"file_id": ...} or URLs.
            if not image_file_id and input_images:
                first = input_images[0] if isinstance(input_images, list) else None
                if isinstance(first, dict):
                    image_file_id = first.get("file_id") or first.get("url")
                elif isinstance(first, str):
                    image_file_id = first  # already a URL or file_id
            if image_file_id:
                try:
                    from core.bot_client import get_bot
                    from core.services import storage
                    # If it's already an http(s) URL (Mini App uploaded to S3
                    # directly), use it as-is; otherwise treat it as a Telegram
                    # file_id and download via the bot.
                    if image_file_id.startswith(("http://", "https://")):
                        params["image_url"] = image_file_id
                    else:
                        bot = get_bot()
                        buf = await bot.download(image_file_id)
                        img_url = await storage.save_upload(buf.read(), "jpg", prefix="video-inputs")
                        params["image_url"] = img_url
                except Exception as exc:  # noqa: BLE001 — best-effort; if upload fails, text2video fallback
                    # FIX: AUDIT-11 - log instead of silent pass
                    log.warning("video.img_upload_failed", job_id=job_id, error=str(exc))

        # Route through admin-configured aggregator accounts (Kie/MuAPI…) first,
        # falling back to the direct env provider; account health is tracked so a
        # throttled aggregator is skipped next time.
        backends = await resolve_backends(
            session, modality="video", model_key=job.service,
            params=params, direct_provider=provider_for(job.service),
        )
        backend, provider_job_id = await submit_or_resume(
            session, backends, existing_provider_job_id=job.provider_job_id,
            existing_backend=(job.params or {}).get("backend"),
        )
        if backend is None:
            await _refund_and_fail(session, job, "provider unavailable")
            return

        job.provider_job_id = provider_job_id
        # Persist which backend owns the provider task so an ARQ retry resumes
        # polling the SAME backend (a multi-backend pool must not poll a peer that
        # doesn't own the task). Reassign params so SQLAlchemy tracks the change.
        job.params = {**(job.params or {}), "backend": backend.name}
        # FIX: F4 - conditional UPDATE WHERE status IN ('pending','processing') AND
        # refunded_at IS NULL so the stuck-job sweep can't have the job refunded
        # between our read and write (was: direct ORM assignment overwrote sweep's
        # 'failed'+'refunded_at' → user got BOTH the delivered video AND the refund).
        # FIX: AUDIT-G3 - accept 'processing' too (not just 'pending'): a job
        # redelivered mid-flight (crashed after submit, before a result) is resumed by
        # submit_or_resume above, so the claim must succeed to actually re-poll it
        # instead of rowcount 0 → silent return → stranded until the 30-min sweep. The
        # refunded_at IS NULL guard still blocks a swept+refunded job.
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

    # Phase B — poll outside the session to avoid holding a connection while we sleep
    for _ in range(MAX_POLLS):
        await asyncio.sleep(POLL_INTERVAL)
        try:
            status = await backend.poll(provider_job_id)
        except Exception as exc:  # noqa: BLE001
            # FIX: AUDIT-11 - log poll failure
            log.warning("video.poll_failed", job_id=job_id, error=str(exc))
            continue
        if status.status == "complete" and status.result_url:
            # Re-host the finished video into OUR storage (no session held during the
            # download) so History/Download survive the provider URL expiring (ТЗ §13).
            # Best-effort: any failure keeps the provider URL — never break a paid result.
            from core.services import storage

            result_url = await storage.rehost_remote(status.result_url) or status.result_url
            # Persist the result URL BEFORE delivery so an ARQ retry (e.g. the
            # finalise commit failing after a successful send) resumes at delivery
            # using the stored URL instead of submitting/generating a second time.
            # FIX: SKILL-R1 - conditional UPDATE (WHERE status='processing') instead
            # of read-then-write. The old pattern was a TOCTOU race with the
            # stuck-job sweep: it could flip the row to 'failed'+'refunded_at'
            # between our check and our write, then we'd overwrite result_url on a
            # refunded row → user could play video after refund via /api/jobs/{id}.
            from sqlalchemy import update as _upd
            async with SessionFactory() as session:
                claim = await session.execute(
                    _upd(GenerationJob)
                    .where(GenerationJob.job_id == job_id, GenerationJob.status == "processing")
                    .values(result_url=result_url)
                )
                if claim.rowcount == 0:
                    return  # already finalised/refunded by another attempt
                await session.commit()
            await _deliver_and_finalise(job_id, result_url)
            return
        if status.status == "failed":
            async with SessionFactory() as session:
                job = await session.get(GenerationJob, job_id)
                # Re-check status: the stuck-job sweep may have already failed +
                # refunded this job. Refunding again here would double-refund.
                if job is None or job.status != "processing":
                    return
                await _refund_and_fail(session, job, status.error or "provider failed")
            return

    # timed out
    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        # Same guard as the failure path: a concurrent sweep may have already
        # resolved (failed + refunded) this job — don't refund a second time.
        if job is None or job.status != "processing":
            return
        await _refund_and_fail(session, job, "timeout")
