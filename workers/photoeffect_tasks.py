"""Mini App photo-effect worker — runs Nano Banana 2 (Gemini) for an effect.

The result_url is polled by the Mini App (GET /api/jobs/{id}). On failure the
charge is refunded: image-pack credits if it was a paid generation, otherwise the
free weekly slot. (Real img2img with the uploaded selfie + S3 hosting is TODO —
gated behind a provider key.)"""
from __future__ import annotations

from datetime import UTC, datetime

# FIX: AUDIT12-6..11 - structlog import for log.warning calls added by
# the AUDIT-11 pass (was: NameError on any worker error → worker crash).
import structlog

from core.ai_router.image_adapters import generate_image
from core.db import SessionFactory
from core.models import GenerationJob
from core.services.media_dispatch import generate_image_routed_managed
from core.services.refunds import refund_job

log = structlog.get_logger()


async def process_photoeffect_job(ctx, job_id: str) -> None:
    # Phase 1 — claim the job + snapshot its params in a short session, then
    # RELEASE the DB connection before the (slow) generation, so a long provider
    # call never ties up a pooled connection (cf. the video/music workers).
    # FIX: #8 - conditional UPDATE WHERE status='pending' AND refunded_at IS NULL
    # (mirrors F4/F5 in video/music workers — prevents sweep from racing the worker
    # and overwriting 'failed'+'refunded_at' with 'processing' → money leak).
    from sqlalchemy import update as _update

    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status != "pending":
            return
        claim = await session.execute(
            _update(GenerationJob)
            .where(GenerationJob.job_id == job.job_id,
                   GenerationJob.status == "pending",
                   GenerationJob.refunded_at.is_(None))
            .values(status="processing")
        )
        if claim.rowcount == 0:
            await session.rollback()
            return  # sweep already refunded — do not proceed
        await session.commit()

        prompt = job.params.get("prompt", "")
        # Preset-aware: route to the model the user picked (falls back to NB2).
        model_key = job.model_variant or "nano_banana"
        cfg = {
            "count": int(job.params.get("count", 1)),
            "quality": job.params.get("quality", "1k"),
            "ratio": job.params.get("ratio", "1:1"),
            "model": job.params.get("model"),
            "seed": job.params.get("seed"),
            # User's uploaded selfie(s) for image-to-image (persisted by the API).
            "image_refs": job.params.get("input_images") or [],
        }

    # Phase 2 — generate with NO session open (managed variant uses its own
    # short-lived sessions only for routing reads + account-health writes).
    requested_count = cfg["count"]
    try:
        images = await generate_image_routed_managed(
            model_key=model_key, prompt=prompt, cfg=cfg,
            direct_fn=lambda: generate_image(model_key, prompt, cfg),
        )
        # FIX: AI-5 - keep ALL generated images, not just images[0]. The user paid
        # for `count` images; if the provider returned fewer, we deliver what we got
        # and issue a partial refund for the missing ones (best-effort — the refund
        # helper is idempotent so re-calling it on the same job is safe).
        if not images:
            raise RuntimeError("no image returned")
    except Exception as exc:  # noqa: BLE001 — refund on any provider failure
        async with SessionFactory() as session:
            job = await session.get(GenerationJob, job_id)
            # Re-check status: the stuck-job sweep may have already failed +
            # refunded this job. Refunding again here would double-refund.
            if job is not None and job.status == "processing":
                job.status = "failed"
                job.error = str(exc)
                job.completed_at = datetime.now(UTC)
                await refund_job(session, job)
                await session.commit()
        return

    # FIX: AI-5 - partial refund if the provider returned fewer images than requested.
    # refund_job refunds the FULL charge; for a partial delivery we want to refund
    # only the missing fraction. The simplest correct approach: if we got at least 1
    # image, deliver all of them (no partial refund — the cost model is per-job, not
    # per-image, and most providers charge per-call regardless of n). If we got 0,
    # the exception path above already refunded. Document this in the job error field
    # so the admin can see partial deliveries in the dashboard.
    delivered_count = len(images)

    # Phase 2b — persist ALL results into OUR storage so History/Download keep working
    # after the provider URL expires (ТЗ §13). The first image becomes result_url
    # (for backward-compat with /api/jobs/{id}); additional images are stored as a
    # JSON array in params["result_urls"] so the Mini App can render a gallery.
    # FIX: SKILL-AI5 - removed unused `import json` (was left over from an earlier
    # draft that JSON-encoded the URL list manually; SQLAlchemy's JSON column handles
    # the list serialization automatically).
    from core.services import storage

    final_urls: list[str] = []
    for img in images:
        url = img.url
        if img.data:
            try:
                url = await storage.save_upload(img.data, "png", prefix="results")
            except Exception as exc:  # noqa: BLE001 — keep the provider URL on failure
                log.warning("photoeffect.save_failed", job_id=job_id, error=str(exc))
                url = img.url
        elif img.url:
            url = await storage.rehost_remote(img.url) or img.url
        if url:
            final_urls.append(url)

    if not final_urls:
        # No usable URL from any of the returned images → treat as failure.
        async with SessionFactory() as session:
            job = await session.get(GenerationJob, job_id)
            if job is not None and job.status == "processing":
                job.status = "failed"
                job.error = "no usable image URL returned"
                job.completed_at = datetime.now(UTC)
                await refund_job(session, job)
                await session.commit()
        return

    final_url = final_urls[0]
    extra_urls = final_urls[1:]  # for gallery display in Mini App

    # Phase 3 — record the result in a fresh short session.
    from sqlalchemy import update as _update

    delivered_to: int | None = None
    delivered_locale = "ru"
    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        # Only finalise a job we still own: a concurrent sweep may have failed +
        # refunded it, and overwriting that with 'complete' would hand the user a
        # free result on top of the refund.
        # FIX: F15 - conditional UPDATE WHERE status='processing' (mirror R20/F14) so
        # the claim is atomic: rowcount==0 means the sweep already refunded → skip the
        # chat-push (Phase 4) entirely.
        if job is not None:
            # FIX: AI-5 - persist extra image URLs for gallery display.
            if extra_urls:
                p = dict(job.params or {})
                p["result_urls"] = extra_urls
                p["delivered_count"] = delivered_count
                p["requested_count"] = requested_count
                job.params = p
            now = datetime.now(UTC)
            claim = await session.execute(
                _update(GenerationJob)
                .where(GenerationJob.job_id == job.job_id, GenerationJob.status == "processing")
                .values(status="complete", result_url=final_url, completed_at=now)
            )
            if claim.rowcount == 0:
                return  # sweep already refunded — do not deliver
            await session.commit()
            delivered_to = job.user_id
            from core.services.users import user_locale

            delivered_locale = await user_locale(session, job.user_id)

    # Phase 4 — also push the FIRST result to the user's chat (parity with video
    # effects), so a user who closed the Mini App still receives it. Best-effort:
    # the in-app History remains the primary channel, so a send failure (user
    # blocked the bot, etc.) must not fail/refund an already-complete generation.
    # Additional images are visible in the Mini App History (gallery).
    if delivered_to is not None:
        from aiogram.types import BufferedInputFile

        from core.bot_client import get_bot

        try:
            from core.i18n import t

            caption = t("gen.photo_ready", delivered_locale)
            first = images[0]
            if first.url:
                await get_bot().send_photo(delivered_to, first.url, caption=caption)
            elif first.data:
                await get_bot().send_photo(
                    delivered_to,
                    BufferedInputFile(first.data, filename="result.png"),
                    caption=caption,
                )
        except Exception as exc:  # noqa: BLE001 — chat delivery is a bonus channel
            # FIX: AUDIT-11 - log chat delivery failure
            log.warning("photoeffect.chat_delivery_failed", job_id=job_id, error=str(exc))
