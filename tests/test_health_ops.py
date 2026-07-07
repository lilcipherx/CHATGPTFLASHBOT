"""Admin System Health + queue/retry/cancel (api/admin/health) — ТЗ §8.

Calls the endpoint coroutines directly against a real SQLite DB, mirroring
tests/test_business_admin.
"""
from __future__ import annotations

import types
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException

from api.admin import health
from core.db import SessionFactory, engine
from core.models import AdminUser, Base, GenerationJob, User
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req():
    return types.SimpleNamespace(client=None)


async def _admin(session, role="admin") -> AdminUser:
    a = AdminUser(email="h@x.io", password_hash=hash_password("x"), role=role, is_active=True)
    session.add(a)
    await session.commit()
    return a


def _old(minutes: int) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)


async def _seed_jobs(session) -> dict:
    """Seed a spread of jobs. Returns key job_ids for assertions."""
    stale = health.STUCK_AFTER_SECONDS // 60 + 5  # comfortably past the threshold
    fresh_pending = GenerationJob(user_id=1, service="suno", pack_type="music",
                                  cost_credits=1, status="pending", created_at=_old(1))
    stuck_processing = GenerationJob(user_id=1, service="kling", pack_type="video",
                                     cost_credits=2, status="processing", created_at=_old(stale))
    completed = GenerationJob(user_id=2, service="suno", status="complete", created_at=_old(stale))
    failed = GenerationJob(user_id=2, service="suno", status="failed",
                           error="boom", created_at=_old(stale))
    session.add_all([fresh_pending, stuck_processing, completed, failed])
    await session.commit()
    return {
        "fresh": fresh_pending.job_id,
        "stuck": stuck_processing.job_id,
        "completed": completed.job_id,
        "failed": failed.job_id,
    }


async def test_queue_health_counts_and_stuck_list():
    async with SessionFactory() as s:
        a = await _admin(s)
        ids = await _seed_jobs(s)
        out = await health.queue_health(admin=a, session=s)

    assert out["counts"]["pending"] == 1
    assert out["counts"]["processing"] == 1
    assert out["counts"]["complete"] == 1
    assert out["counts"]["failed"] == 1
    # Only the old processing job is stuck (fresh pending is under the threshold;
    # completed/failed are terminal).
    assert out["stuck_count"] == 1
    stuck_ids = {j["job_id"] for j in out["stuck_jobs"]}
    assert str(ids["stuck"]) in stuck_ids
    assert str(ids["fresh"]) not in stuck_ids
    assert out["oldest_pending_age_seconds"] > 0


async def test_system_health_db_true():
    async with SessionFactory() as s:
        a = await _admin(s)
        await _seed_jobs(s)
        out = await health.system_health(admin=a, session=s)
    assert out["db_ok"] is True
    assert out["total_users"] == 0  # no User rows seeded
    assert out["pending_jobs"] == 2  # pending + processing
    assert isinstance(out["redis_ok"], bool)
    # liveness extras: latency / error-rate / uptime / version are always present
    assert isinstance(out["avg_job_seconds"], (int, float))
    assert isinstance(out["error_rate_pct"], (int, float))
    assert out["uptime_seconds"] >= 0
    assert isinstance(out["version"], str) and out["version"]


async def test_retry_resets_stuck_active_job_to_pending():
    async with SessionFactory() as s:
        a = await _admin(s)
        ids = await _seed_jobs(s)
        # The stuck (old, processing) job — its charge still stands, so it is retryable.
        out = await health.retry_job(str(ids["stuck"]), _req(), admin=a, session=s)
        assert out["status"] == "pending"
        job = await s.get(GenerationJob, ids["stuck"])
        assert job.status == "pending"
        assert job.error is None


async def test_retry_rejects_failed_job_money_safety():
    """A failed job was already refunded, so re-running it would double-refund (on a
    second failure) or give a free result (on success). Retry must reject it and leave
    it untouched. Regression for the admin-retry money bug."""
    async with SessionFactory() as s:
        a = await _admin(s)
        ids = await _seed_jobs(s)
        with pytest.raises(HTTPException) as exc:
            await health.retry_job(str(ids["failed"]), _req(), admin=a, session=s)
        assert exc.value.status_code == 400
        # The failed job must NOT be reset to pending (no silent re-enqueue).
        job = await s.get(GenerationJob, ids["failed"])
        assert job.status == "failed"


async def test_retry_rejects_completed_job():
    async with SessionFactory() as s:
        a = await _admin(s)
        ids = await _seed_jobs(s)
        with pytest.raises(HTTPException) as exc:
            await health.retry_job(str(ids["completed"]), _req(), admin=a, session=s)
        assert exc.value.status_code == 400


async def test_retry_rejects_fresh_active_job():
    """A fresh (not-yet-stuck) active job is being worked on normally — retrying it
    would spawn a duplicate worker, so it must be rejected until it is actually stuck."""
    async with SessionFactory() as s:
        a = await _admin(s)
        ids = await _seed_jobs(s)
        with pytest.raises(HTTPException) as exc:
            await health.retry_job(str(ids["fresh"]), _req(), admin=a, session=s)
        assert exc.value.status_code == 400


async def test_cancel_marks_failed_and_refunds_credits():
    async with SessionFactory() as s:
        a = await _admin(s)
        s.add(User(user_id=99, credits=0))
        job = GenerationJob(user_id=99, service="suno", pack_type="credits",
                            cost_credits=15, status="processing", created_at=_old(1))
        s.add(job)
        await s.commit()
        job_id = job.job_id

        out = await health.cancel_job(str(job_id), _req(), admin=a, session=s)
        assert out["status"] == "failed"
        assert out["refunded"] is True

    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        assert job.status == "failed"
        user = await s.get(User, 99)
        assert user.credits == 15  # charge returned


async def test_cancel_idempotent_no_double_refund():
    async with SessionFactory() as s:
        a = await _admin(s)
        s.add(User(user_id=77, credits=0))
        job = GenerationJob(user_id=77, service="suno", pack_type="credits",
                            cost_credits=10, status="pending", created_at=_old(1))
        s.add(job)
        await s.commit()
        job_id = job.job_id

        await health.cancel_job(str(job_id), _req(), admin=a, session=s)
        second = await health.cancel_job(str(job_id), _req(), admin=a, session=s)
        assert second["refunded"] is False

    async with SessionFactory() as s:
        user = await s.get(User, 77)
        assert user.credits == 10  # refunded exactly once
