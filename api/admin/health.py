"""Admin: System Health + queue health, retry/cancel stuck jobs (ТЗ §8).

Read-only health views plus two write actions over the existing GenerationJob:
  * retry  — reset a failed/stuck job back to "pending" so the worker reprocesses
             it (best-effort re-enqueue via core.queue);
  * cancel — mark a pending/processing job failed and refund the charge, mirroring
             the stuck-job sweep's refund (idempotent — no double refund).

Mounted at /health-ops to avoid clashing with the public /health probe.
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core.config import settings
from core.db import get_session
from core.models import AdminUser, GenerationJob, User
from core.redis_client import redis_client
from core.services.refunds import refund_job
from core.timeutils import ensure_aware

router = APIRouter(prefix="/health-ops", tags=["admin-health"])
log = structlog.get_logger()

# Process start — module import happens once at app boot, so this is a good-enough
# uptime origin without threading state through the lifespan.
_STARTED_AT = datetime.now(UTC)
# Build version: set APP_VERSION in the deploy env (e.g. the git short SHA); "dev"
# locally. Never raises — purely informational.
_VERSION = os.getenv("APP_VERSION") or "dev"
# Window for the rolling latency / error-rate health stats.
_STATS_WINDOW = timedelta(hours=24)

# Mirror the worker sweep's definition of "stuck": a pending/processing job older
# than the configured ceiling was almost certainly abandoned mid-run.
STUCK_AFTER_SECONDS = settings.stuck_job_minutes * 60
_ACTIVE = ("pending", "processing")


# Map a job back to the ARQ worker that processes it, so a retry re-enqueues to
# the right pool. Photo tools / avatar / photoeffect have dedicated workers keyed
# on the exact service string; everything else falls back on pack_type (music vs
# video). Re-enqueue is best-effort, so an unmapped service simply skips enqueue
# and relies on the status reset for a worker to pick it up.
_SERVICE_WORKER = {
    "avatar": "process_avatar_job",
    "faceswap": "process_faceswap_job",
    "upscale": "process_upscale_job",
    "photoeffect": "process_photoeffect_job",
    "suno": "process_music_job",
    "lyria": "process_music_job",
}


def _worker_for(job: GenerationJob) -> str | None:
    worker = _SERVICE_WORKER.get(job.service)
    if worker:
        return worker
    if job.pack_type == "music":
        return "process_music_job"
    if job.pack_type == "video":
        return "process_video_job"
    return None


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _stale_cutoff() -> datetime:
    return datetime.now(UTC) - timedelta(seconds=STUCK_AFTER_SECONDS)


@router.get("/queue")
async def queue_health(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Counts by status, number of stuck jobs, oldest pending age, and a small list
    of recent stuck jobs for the ops table."""
    cutoff = _stale_cutoff()

    rows = (await session.execute(
        select(GenerationJob.status, func.count()).group_by(GenerationJob.status)
    )).all()
    counts = {s: int(n) for s, n in rows}

    stuck_total = await session.scalar(
        select(func.count()).select_from(GenerationJob).where(
            GenerationJob.status.in_(_ACTIVE),
            GenerationJob.created_at < cutoff,
        )
    )

    oldest_pending = await session.scalar(
        select(func.min(GenerationJob.created_at)).where(
            GenerationJob.status.in_(_ACTIVE)
        )
    )
    oldest_pending_age_seconds = (
        (datetime.now(UTC) - ensure_aware(oldest_pending)).total_seconds()
        if oldest_pending is not None else 0.0
    )

    stuck_rows = (await session.scalars(
        select(GenerationJob)
        .where(
            GenerationJob.status.in_(_ACTIVE),
            GenerationJob.created_at < cutoff,
        )
        .order_by(GenerationJob.created_at.asc())
        .limit(50)
    )).all()

    return {
        "counts": counts,
        "stuck_count": int(stuck_total or 0),
        "stuck_threshold_seconds": STUCK_AFTER_SECONDS,
        "oldest_pending_age_seconds": oldest_pending_age_seconds,
        "stuck_jobs": [
            {
                "job_id": str(j.job_id),
                "service": j.service,
                "user_id": j.user_id,
                "status": j.status,
                "created_at": ensure_aware(j.created_at).isoformat(),
            }
            for j in stuck_rows
        ],
    }


@router.get("/system")
async def system_health(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Lightweight liveness: DB + Redis reachability and a couple of counts. Never
    raises — any probe failure is reported as a false/zero so the panel can render."""
    db_ok = False
    total_users = 0
    pending_jobs = 0
    try:
        await session.execute(select(1))
        db_ok = True
        total_users = int(await session.scalar(
            select(func.count()).select_from(User)
        ) or 0)
        pending_jobs = int(await session.scalar(
            select(func.count()).select_from(GenerationJob).where(
                GenerationJob.status.in_(_ACTIVE)
            )
        ) or 0)
    except Exception:  # noqa: BLE001 — health probe must never raise
        log.warning("system_health.db_unreachable")

    redis_ok = False
    try:
        redis_ok = bool(await redis_client.ping())
    except Exception:  # noqa: BLE001 — best-effort
        log.warning("system_health.redis_unreachable")

    # Rolling 24h latency + error rate (best-effort; any failure → zeros).
    avg_job_seconds = 0.0
    error_rate_pct = 0.0
    completed_24h = 0
    failed_24h = 0
    try:
        window = datetime.now(UTC) - _STATS_WINDOW
        # Average wall-clock duration of recently completed jobs. Computed in Python
        # over a bounded recent sample so it stays portable (no DB-specific date math).
        dur_rows = (await session.execute(
            select(GenerationJob.created_at, GenerationJob.completed_at).where(
                GenerationJob.status == "complete",
                GenerationJob.completed_at.is_not(None),
                GenerationJob.created_at >= window,
            ).order_by(GenerationJob.completed_at.desc()).limit(500)
        )).all()
        durations = [
            (ensure_aware(done) - ensure_aware(start)).total_seconds()
            for start, done in dur_rows
            if done is not None and start is not None
        ]
        durations = [d for d in durations if d >= 0]
        if durations:
            avg_job_seconds = round(sum(durations) / len(durations), 1)

        completed_24h = int(await session.scalar(
            select(func.count()).select_from(GenerationJob).where(
                GenerationJob.status == "complete", GenerationJob.created_at >= window,
            )
        ) or 0)
        failed_24h = int(await session.scalar(
            select(func.count()).select_from(GenerationJob).where(
                GenerationJob.status == "failed", GenerationJob.created_at >= window,
            )
        ) or 0)
        finished = completed_24h + failed_24h
        if finished:
            error_rate_pct = round(failed_24h / finished * 100, 1)
    except Exception:  # noqa: BLE001 — stats are best-effort; never break the probe
        log.warning("system_health.stats_failed")

    return {
        "db_ok": db_ok,
        "redis_ok": redis_ok,
        "total_users": total_users,
        "pending_jobs": pending_jobs,
        "avg_job_seconds": avg_job_seconds,
        "error_rate_pct": error_rate_pct,
        "completed_24h": completed_24h,
        "failed_24h": failed_24h,
        "uptime_seconds": int((datetime.now(UTC) - _STARTED_AT).total_seconds()),
        "version": _VERSION,
    }


def _parse_job_id(job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="not found") from None


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: str, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Reset a STUCK active job to "pending" so the worker reprocesses it.

    Re-enqueue is best-effort. If it fails (Redis/ARQ down), the status reset is NOT
    silently lost: the billing stuck-job sweep will refund + fail the job once it
    passes the ceiling again (only avatar jobs have a dedicated pending re-enqueue
    sweep, `claim_pending_avatars`). So a retry that can't enqueue costs the user
    nothing — they are refunded — it just won't reprocess.

    Only a stuck *active* (pending/processing past the threshold) job is retryable —
    its charge still stands, so reprocessing is fair. A "failed" job was ALREADY
    refunded by its failure path (every failure calls refund_job), so re-running it
    would hand the user a free result on success. (refund_job is now idempotent per
    job, so a re-fail can't double-refund — but the free-result-on-success case is
    reason enough to keep this gated.) The page UI only ever lists stuck active jobs,
    so this restriction matches what the table exposes.
    """
    pk = _parse_job_id(job_id)
    job = await session.get(GenerationJob, pk)
    if job is None:
        raise HTTPException(status_code=404, detail="not found")

    cutoff = _stale_cutoff()
    is_stuck = job.status in _ACTIVE and ensure_aware(job.created_at) < cutoff
    if not is_stuck:
        raise HTTPException(
            status_code=400, detail="job not retryable (stuck active jobs only)"
        )

    before = {"status": job.status}
    # FIX: R14 - atomic conditional UPDATE so a concurrent retry (or the stuck-job
    # sweep) that already moved this row out of _ACTIVE can't be overwritten by our
    # reset. On rowcount==0 the job is no longer retryable — surface a 409.
    now = datetime.now(UTC)
    res = await session.execute(
        update(GenerationJob)
        .where(GenerationJob.job_id == pk, GenerationJob.status.in_(_ACTIVE))
        .values(status="pending", error=None, completed_at=None, created_at=now)
    )
    if res.rowcount == 0:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="job state changed concurrently — reload and retry"
        )
    await session.commit()

    enqueued = False
    worker = _worker_for(job)
    if worker is not None:
        try:
            from core.queue import enqueue

            await enqueue(worker, str(job.job_id))
            enqueued = True
        except Exception as exc:  # noqa: BLE001 — re-enqueue is best-effort
            log.warning("retry_job.enqueue_failed", job=str(job.job_id), error=str(exc))

    await audit(session, admin_id=admin.id, action="job.retry", target_type="generation_job",
                target_id=job_id, before=before,
                after={"status": "pending", "enqueued": enqueued}, ip=_ip(request))
    return {"ok": True, "job_id": job_id, "status": "pending", "enqueued": enqueued}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Mark a pending/processing job failed and refund the charge.

    Idempotent: the terminal transition is a conditional UPDATE that only matches a
    still-active job, so a job already failed (by a worker or a concurrent cancel)
    is a no-op and is never refunded twice.
    """
    pk = _parse_job_id(job_id)
    job = await session.get(GenerationJob, pk)
    if job is None:
        raise HTTPException(status_code=404, detail="not found")
    if job.status not in _ACTIVE:
        # Already terminal — do not refund again.
        return {"ok": True, "job_id": job_id, "status": job.status, "refunded": False}

    claimed = await session.execute(
        update(GenerationJob)
        .where(
            GenerationJob.job_id == pk,
            GenerationJob.status.in_(_ACTIVE),
        )
        .values(
            status="failed",
            error="cancelled by admin",
            completed_at=datetime.now(UTC),
        )
    )
    if claimed.rowcount == 0:
        await session.rollback()
        fresh = await session.get(GenerationJob, pk)
        return {
            "ok": True, "job_id": job_id,
            "status": fresh.status if fresh else "failed", "refunded": False,
        }

    job = await session.get(GenerationJob, pk)
    if job is not None:
        await refund_job(session, job)  # canonical 🪙/pack/free-slot/stars reversal
    # FIX: AUDIT12-15 - fold audit into the same tx as the refund+status commit.
    await audit(session, admin_id=admin.id, action="job.cancel", target_type="generation_job",
                target_id=job_id, after={"status": "failed"}, ip=_ip(request), commit=False)
    await session.commit()
    return {"ok": True, "job_id": job_id, "status": "failed", "refunded": True}
