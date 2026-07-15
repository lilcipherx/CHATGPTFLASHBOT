"""Face Swap + Upscale workers (§15A) — route through the media-gateway pool.

Mirrors workers/video_tasks.py: upload input photo(s) → resolve_backends(image) →
submit_or_resume → poll → rehost → deliver → refund-on-failure. When no gateway
account is configured the pool is empty, so the job refunds + notifies (the previous
stub behaviour is preserved for the unconfigured case)."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy import update

from core.db import SessionFactory
from core.models import GenerationJob
from core.services.media_dispatch import resolve_backends, submit_or_resume
from core.services.refunds import refund_job

log = structlog.get_logger()

POLL_INTERVAL = 5       # seconds between polls
MAX_POLLS = 60          # ~5 min ceiling (photo tools are faster than video)


async def _notify_unavailable(user_id: int) -> None:
    """Tell the user the tool is unavailable and the credit was returned. Best-effort."""
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
    await refund_job(session, job)  # canonical credit/pack reversal (idempotent)
    await session.commit()


async def _upload_file_id(file_id: str, job_id: str | None = None) -> str | None:
    """Download a Telegram file_id and re-host to storage; return a fetchable URL.
    An http(s) value is passed through. Returns None on any failure."""
    if not file_id:
        return None
    try:
        if file_id.startswith(("http://", "https://")):
            return file_id
        from core.bot_client import get_bot
        from core.services import storage

        buf = await get_bot().download(file_id)
        return await storage.save_upload(buf.read(), "jpg", prefix="tool-inputs")
    except Exception as exc:  # noqa: BLE001 — a bad/expired file_id fails the job → refund
        log.warning("phototool.input_upload_failed", job_id=job_id, error=str(exc))
        return None


async def _deliver_image(job: GenerationJob, result_url: str, locale: str) -> None:
    from core.bot_client import get_bot

    await get_bot().send_photo(job.user_id, result_url)


async def _deliver_and_finalise(job_id: str, result_url: str) -> None:
    """Idempotently deliver the finished image and mark the job complete. Chat is the
    only channel for these tools, so a send failure flips the job back to failed +
    refund (parity with video_tasks' bot branch)."""
    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status == "complete":
            return
        from core.services.users import user_locale

        locale = await user_locale(session, job.user_id)
        now = datetime.now(UTC)
        claim = await session.execute(
            update(GenerationJob)
            .where(GenerationJob.job_id == job.job_id, GenerationJob.status == "processing")
            .values(status="complete", result_url=result_url, completed_at=now)
        )
        if claim.rowcount == 0:
            return  # another attempt already finalised
        await session.commit()
        try:
            await _deliver_image(job, result_url, locale)
        except Exception as exc:  # noqa: BLE001 — delivery failed after claim → refund
            async with SessionFactory() as fail_session:
                fail_job = await fail_session.get(GenerationJob, job_id)
                if fail_job is not None and fail_job.status == "complete":
                    await _refund_and_fail(fail_session, fail_job, f"deliver: {exc}")
            return


async def _run_tool_job(
    ctx, job_id: str, *, model_key: str,
    file_params: dict[str, str | None], extra_params: dict,
) -> None:
    """Shared submit→poll→deliver→refund pipeline for image tools (faceswap/upscale).

    ``file_params`` maps a provider input field → a Telegram file_id (uploaded to a
    URL before submit). ``extra_params`` are passed to the gateway verbatim."""
    # Phase A — claim, upload inputs, submit.
    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status not in ("pending", "processing"):
            return
        if job.result_url:
            await _deliver_and_finalise(job_id, job.result_url)
            return

        params = dict(extra_params)
        for field, file_id in file_params.items():
            if not file_id:
                await _refund_and_fail(session, job, f"missing input: {field}")
                return
            url = await _upload_file_id(file_id, job_id)
            if not url:
                await _refund_and_fail(session, job, f"input upload failed: {field}")
                return
            params[field] = url

        backends = await resolve_backends(
            session, modality="image", model_key=model_key,
            params=params, direct_provider=None,
        )
        backend, provider_job_id = await submit_or_resume(
            session, backends, existing_provider_job_id=job.provider_job_id,
            existing_backend=(job.params or {}).get("backend"),
        )
        if backend is None:
            await _refund_and_fail(session, job, f"{model_key} provider not configured")
            await _notify_unavailable(job.user_id)
            return

        claim = await session.execute(
            update(GenerationJob)
            .where(GenerationJob.job_id == job.job_id,
                   GenerationJob.status.in_(("pending", "processing")),
                   GenerationJob.refunded_at.is_(None))
            .values(status="processing", provider_job_id=provider_job_id,
                    params={**(job.params or {}), "backend": backend.name})
        )
        if claim.rowcount == 0:
            await session.rollback()
            return
        await session.commit()

    # Phase B — poll outside the session.
    for _ in range(MAX_POLLS):
        await asyncio.sleep(POLL_INTERVAL)
        try:
            status = await backend.poll(provider_job_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("phototool.poll_failed", job_id=job_id, error=str(exc))
            continue
        if status.status == "complete" and status.result_url:
            from core.services import storage

            result_url = await storage.rehost_remote(status.result_url) or status.result_url
            async with SessionFactory() as session:
                claim = await session.execute(
                    update(GenerationJob)
                    .where(GenerationJob.job_id == job_id, GenerationJob.status == "processing")
                    .values(result_url=result_url)
                )
                if claim.rowcount == 0:
                    return
                await session.commit()
            await _deliver_and_finalise(job_id, result_url)
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


async def process_faceswap_job(ctx, job_id: str) -> None:
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        params = (job.params or {}) if job else {}
    await _run_tool_job(
        ctx, job_id, model_key="faceswap",
        file_params={"target_image": params.get("target"),
                     "source_image": params.get("source")},
        extra_params={},
    )


async def process_upscale_job(ctx, job_id: str) -> None:
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        params = (job.params or {}) if job else {}
    factor = params.get("factor", "x2")
    scale = 4 if factor == "x4" else 2
    await _run_tool_job(
        ctx, job_id, model_key="upscale",
        file_params={"image": params.get("image")},
        extra_params={"scale": scale},
    )
