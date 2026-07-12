"""ARQ-retry idempotency for the submit→poll→deliver workers (M2): a retried job
must not submit/generate a second provider task nor deliver the media twice."""
from __future__ import annotations

import pytest_asyncio

from core.ai_router.base import JobStatus
from core.db import SessionFactory, engine
from core.models import Base, GenerationJob
from core.services.media_dispatch import submit_or_resume
from workers import video_tasks


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _job(**kw):
    async with SessionFactory() as s:
        job = GenerationJob(
            user_id=1, service="kling_ai", status=kw.get("status", "pending"),
            pack_type="video", cost_credits=1, params={},
            result_url=kw.get("result_url"), provider_job_id=kw.get("provider_job_id"),
        )
        s.add(job)
        await s.commit()
        return job.job_id  # uuid.UUID (valid key for SQLite + Postgres)


class _FakeBackend:
    account_id = None
    name = "fake#1"

    async def submit(self):  # pragma: no cover — must never be called on resume
        raise AssertionError("submit() must not be called when resuming")

    async def poll(self, tid):
        return JobStatus("complete", result_url="https://x/v.mp4")


# ---- submit_or_resume ------------------------------------------------------
async def test_submit_or_resume_resumes_without_submitting():
    backend, tid = await submit_or_resume(
        None, [_FakeBackend()], existing_provider_job_id="ptask-9"
    )
    assert tid == "ptask-9" and backend is not None  # reused, no submit


async def test_submit_or_resume_none_when_no_backends():
    assert await submit_or_resume(None, [], existing_provider_job_id="x") == (None, None)


class _NamedBackend(_FakeBackend):
    def __init__(self, name):
        self.name = name


async def test_submit_or_resume_targets_owning_backend():
    # A multi-backend pool must resume on the backend that OWNS the provider task,
    # not whichever happens to be first (polling a peer = false timeout refund).
    a, b = _NamedBackend("kie#1"), _NamedBackend("muapi#2")
    backend, tid = await submit_or_resume(
        None, [a, b], existing_provider_job_id="ptask-7", existing_backend="muapi#2"
    )
    assert backend is b and tid == "ptask-7"


async def test_submit_or_resume_none_when_owner_gone():
    # The owning backend dropped out of the pool → can't safely poll a peer, so
    # signal "no backend" and let the caller refund rather than poll the wrong one.
    backend, tid = await submit_or_resume(
        None, [_NamedBackend("kie#1")], existing_provider_job_id="ptask-7",
        existing_backend="muapi#2",
    )
    assert backend is None and tid is None


# ---- worker delivery idempotency -------------------------------------------
async def test_happy_path_then_retry_delivers_once(monkeypatch):
    delivered: list[str] = []

    async def _fake_deliver(job, url, locale="ru"):
        delivered.append(url)

    async def _fake_resolve(*a, **k):
        return [_FakeBackend()]

    async def _fake_submit_or_resume(
        session, backends, *, existing_provider_job_id, existing_backend=None
    ):
        return _FakeBackend(), existing_provider_job_id or "ptask-1"

    monkeypatch.setattr(video_tasks, "POLL_INTERVAL", 0)  # don't actually sleep
    monkeypatch.setattr(video_tasks, "_deliver", _fake_deliver)
    monkeypatch.setattr(video_tasks, "resolve_backends", _fake_resolve)
    monkeypatch.setattr(video_tasks, "submit_or_resume", _fake_submit_or_resume)

    job_id = await _job(status="pending")
    await video_tasks.process_video_job(None, job_id)
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        assert job.status == "complete" and job.result_url == "https://x/v.mp4"
    assert delivered == ["https://x/v.mp4"]

    # ARQ redelivers the same job → terminal guard, no second send
    await video_tasks.process_video_job(None, job_id)
    assert delivered == ["https://x/v.mp4"]


async def test_retry_with_result_skips_resolve_and_submit(monkeypatch):
    """The exact M2 window: a prior attempt generated the video (result_url set)
    but crashed before finalising (status still 'processing'). The retry must NOT
    resolve/submit a new provider task — only deliver + finalise."""
    delivered: list[str] = []

    async def _fake_deliver(job, url, locale="ru"):
        delivered.append(url)

    def _boom(*a, **k):
        raise AssertionError("must not resolve/submit when a result already exists")

    monkeypatch.setattr(video_tasks, "_deliver", _fake_deliver)
    monkeypatch.setattr(video_tasks, "resolve_backends", _boom)
    monkeypatch.setattr(video_tasks, "submit_or_resume", _boom)

    job_id = await _job(status="processing", result_url="https://x/v.mp4",
                        provider_job_id="ptask-1")
    await video_tasks.process_video_job(None, job_id)
    assert delivered == ["https://x/v.mp4"]
    async with SessionFactory() as s:
        assert (await s.get(GenerationJob, job_id)).status == "complete"


async def test_resume_processing_job_polls_and_completes(monkeypatch):
    """G-3: a job redelivered while still 'processing' with a provider task but NO
    result_url yet (worker crashed mid-poll) must RESUME polling that task and
    finalise — not hit the Phase-A claim's WHERE status='pending' (rowcount 0) and
    silently return, wasting submit_or_resume and stranding the job until the
    30-min stuck sweep."""
    delivered: list[str] = []

    async def _fake_deliver(job, url, locale="ru"):
        delivered.append(url)

    async def _fake_resolve(*a, **k):
        return [_FakeBackend()]

    async def _fake_submit_or_resume(
        session, backends, *, existing_provider_job_id, existing_backend=None
    ):
        # Resume path: reuse the existing provider task, never submit a new one.
        assert existing_provider_job_id == "ptask-1"
        return _FakeBackend(), existing_provider_job_id

    monkeypatch.setattr(video_tasks, "POLL_INTERVAL", 0)
    monkeypatch.setattr(video_tasks, "_deliver", _fake_deliver)
    monkeypatch.setattr(video_tasks, "resolve_backends", _fake_resolve)
    monkeypatch.setattr(video_tasks, "submit_or_resume", _fake_submit_or_resume)

    job_id = await _job(status="processing", provider_job_id="ptask-1")  # no result_url
    await video_tasks.process_video_job(None, job_id)
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        assert job.status == "complete" and job.result_url == "https://x/v.mp4"
    assert delivered == ["https://x/v.mp4"]  # resumed → polled → delivered once
