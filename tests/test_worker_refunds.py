"""Refund-on-failure for the video generation worker (the money path): every
terminal failure — provider unavailable, provider-reported failure, poll timeout,
and delivery failure — must mark the job ``failed`` AND return the charged video
pack credit. Complements test_worker_idempotency (happy-path + ARQ-retry)."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import select

from core.ai_router.base import JobStatus
from core.db import SessionFactory, engine
from core.models import Base, GenerationJob, PackBalance
from workers import video_tasks


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _video_job():
    async with SessionFactory() as s:
        job = GenerationJob(user_id=1, service="kling_ai", status="pending",
                            pack_type="video", cost_credits=1, params={})
        s.add(job)
        await s.commit()
        return job.job_id


async def _assert_failed_and_refunded(job_id, err_contains: str):
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        assert job.status == "failed"
        assert err_contains in (job.error or "")
        assert job.refunded_at is not None  # the row-claim refund guard fired once
        bal = (await s.execute(
            select(PackBalance).where(PackBalance.user_id == 1)
        )).scalar_one_or_none()
        assert bal is not None and bal.video_credits == 1  # the charged credit came back


class _Backend:
    account_id = None
    name = "fake#1"

    def __init__(self, status: JobStatus):
        self._status = status

    async def poll(self, tid):
        return self._status


def _patch(monkeypatch, backend, *, submit=("be", "tid")):
    async def _backends(*a, **k):
        return [backend] if backend else []

    async def _submit(*a, **k):
        return (backend, submit[1]) if backend else (None, None)

    monkeypatch.setattr(video_tasks, "POLL_INTERVAL", 0)
    monkeypatch.setattr(video_tasks, "resolve_backends", _backends)
    monkeypatch.setattr(video_tasks, "submit_or_resume", _submit)


async def test_provider_unavailable_refunds(monkeypatch):
    _patch(monkeypatch, None)  # no backend → submit_or_resume returns (None, None)
    job_id = await _video_job()
    await video_tasks.process_video_job(None, job_id)
    await _assert_failed_and_refunded(job_id, "provider unavailable")


async def test_provider_reported_failure_refunds(monkeypatch):
    _patch(monkeypatch, _Backend(JobStatus("failed", error="boom")))
    job_id = await _video_job()
    await video_tasks.process_video_job(None, job_id)
    await _assert_failed_and_refunded(job_id, "boom")


async def test_poll_timeout_refunds(monkeypatch):
    _patch(monkeypatch, _Backend(JobStatus("processing")))  # never completes
    monkeypatch.setattr(video_tasks, "MAX_POLLS", 1)
    job_id = await _video_job()
    await video_tasks.process_video_job(None, job_id)
    await _assert_failed_and_refunded(job_id, "timeout")


async def test_delivery_failure_refunds(monkeypatch):
    _patch(monkeypatch, _Backend(JobStatus("complete", result_url="https://x/v.mp4")))

    async def _boom_deliver(job, url, locale="ru"):
        raise RuntimeError("send failed")

    monkeypatch.setattr(video_tasks, "_deliver", _boom_deliver)
    job_id = await _video_job()
    await video_tasks.process_video_job(None, job_id)
    # The result URL was generated but delivery failed → still refund + fail.
    await _assert_failed_and_refunded(job_id, "deliver")
