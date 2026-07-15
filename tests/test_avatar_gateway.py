"""Avatar routes through the media-gateway pool: a configured backend delivers the
result images as albums; every terminal failure marks the job failed + refunds."""
from __future__ import annotations

import pytest_asyncio

from core.ai_router.base import JobStatus
from core.db import SessionFactory, engine
from core.models import Base, GenerationJob
from workers import avatar_tasks as at


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _avatar_job(count=3):
    async with SessionFactory() as s:
        job = GenerationJob(user_id=1, service="avatar", status="pending",
                            pack_type="stars", cost_credits=0,
                            params={"selfie_file_id": "self_fid", "count": count,
                                    "charge_id": "ch_1"})
        s.add(job)
        await s.commit()
        return job.job_id


class _Backend:
    account_id = None
    name = "fake#1"

    def __init__(self, status: JobStatus):
        self._status = status

    async def poll(self, tid):
        return self._status


def _patch(monkeypatch, backend, *, delivered: list | None = None, refunds: list | None = None):
    async def _backends(*a, **k):
        return [backend] if backend else []

    async def _submit(*a, **k):
        return (backend, "tid") if backend else (None, None)

    async def _upload(file_id, job_id=None):
        return f"https://s3/{file_id}.jpg"

    async def _rehost(url, **k):
        return url

    async def _albums(user_id, urls):
        if delivered is not None:
            delivered.extend(urls)
        return len(urls)

    async def _refund(session, job):
        if refunds is not None:
            refunds.append(job.job_id)

    monkeypatch.setattr(at, "POLL_INTERVAL", 0)
    monkeypatch.setattr(at, "resolve_backends", _backends)
    monkeypatch.setattr(at, "submit_or_resume", _submit)
    monkeypatch.setattr(at, "_upload_file_id", _upload)
    monkeypatch.setattr(at, "_deliver_albums", _albums)
    monkeypatch.setattr(at, "refund_job", _refund)
    import core.services.storage as storage
    monkeypatch.setattr(storage, "rehost_remote", _rehost)


async def _assert_failed_refunded(job_id, refunds, err_contains):
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        assert job.status == "failed"
        assert err_contains in (job.error or "")
    assert job_id in refunds


async def test_avatar_success_multi_url_delivers(monkeypatch):
    delivered: list = []
    _patch(monkeypatch, _Backend(JobStatus("complete", result_url="https://a/1.png",
           result_urls=["https://a/1.png", "https://a/2.png"])), delivered=delivered)
    job_id = await _avatar_job()
    await at.process_avatar_job(None, job_id)
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        assert job.status == "complete"
    assert delivered == ["https://a/1.png", "https://a/2.png"]


async def test_avatar_success_single_url_delivers(monkeypatch):
    delivered: list = []
    _patch(monkeypatch, _Backend(JobStatus("complete", result_url="https://a/only.png")),
           delivered=delivered)
    job_id = await _avatar_job()
    await at.process_avatar_job(None, job_id)
    assert delivered == ["https://a/only.png"]


async def test_avatar_no_backend_refunds(monkeypatch):
    refunds: list = []
    _patch(monkeypatch, None, refunds=refunds)
    job_id = await _avatar_job()
    await at.process_avatar_job(None, job_id)
    await _assert_failed_refunded(job_id, refunds, "provider not configured")


async def test_avatar_provider_failed_refunds(monkeypatch):
    refunds: list = []
    _patch(monkeypatch, _Backend(JobStatus("failed", error="boom")), refunds=refunds)
    job_id = await _avatar_job()
    await at.process_avatar_job(None, job_id)
    await _assert_failed_refunded(job_id, refunds, "boom")


async def test_avatar_timeout_refunds(monkeypatch):
    refunds: list = []
    _patch(monkeypatch, _Backend(JobStatus("processing")), refunds=refunds)
    monkeypatch.setattr(at, "MAX_POLLS", 1)
    job_id = await _avatar_job()
    await at.process_avatar_job(None, job_id)
    await _assert_failed_refunded(job_id, refunds, "timeout")


async def test_avatar_complete_zero_urls_refunds(monkeypatch):
    refunds: list = []
    _patch(monkeypatch, _Backend(JobStatus("complete")), refunds=refunds)
    job_id = await _avatar_job()
    await at.process_avatar_job(None, job_id)
    await _assert_failed_refunded(job_id, refunds, "no results")


async def test_avatar_missing_selfie_refunds(monkeypatch):
    refunds: list = []
    _patch(monkeypatch, _Backend(JobStatus("processing")), refunds=refunds)
    async with SessionFactory() as s:
        job = GenerationJob(user_id=1, service="avatar", status="pending",
                            pack_type="stars", cost_credits=0,
                            params={"count": 3, "charge_id": "ch_1"})
        s.add(job)
        await s.commit()
        job_id = job.job_id
    await at.process_avatar_job(None, job_id)
    await _assert_failed_refunded(job_id, refunds, "missing selfie")
