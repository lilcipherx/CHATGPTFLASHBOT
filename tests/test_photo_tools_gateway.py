"""Face Swap + Upscale route through the media-gateway pool: a configured backend
delivers, and every terminal failure refunds the charged image credit exactly once."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import select

from core.ai_router.base import JobStatus
from core.db import SessionFactory, engine
from core.models import Base, GenerationJob, PackBalance
from workers import photo_tools_tasks as pt


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _faceswap_job():
    async with SessionFactory() as s:
        job = GenerationJob(user_id=1, service="faceswap", status="pending",
                            pack_type="image", cost_credits=1,
                            params={"target": "tgt_fid", "source": "src_fid"})
        s.add(job)
        await s.commit()
        return job.job_id


async def _assert_failed_and_refunded(job_id, err_contains: str):
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        assert job.status == "failed"
        assert err_contains in (job.error or "")
        assert job.refunded_at is not None
        bal = (await s.execute(
            select(PackBalance).where(PackBalance.user_id == 1)
        )).scalar_one_or_none()
        assert bal is not None and bal.image_credits == 1


class _Backend:
    account_id = None
    name = "fake#1"

    def __init__(self, status: JobStatus):
        self._status = status

    async def poll(self, tid):
        return self._status


def _patch(monkeypatch, backend, *, delivered: list | None = None):
    async def _backends(*a, **k):
        return [backend] if backend else []

    async def _submit(*a, **k):
        return (backend, "tid") if backend else (None, None)

    async def _upload(file_id, job_id=None):
        return f"https://s3/{file_id}.jpg"

    async def _rehost(url, **k):
        return url

    async def _deliver(job, url, locale="ru"):
        if delivered is not None:
            delivered.append(url)

    monkeypatch.setattr(pt, "POLL_INTERVAL", 0)
    monkeypatch.setattr(pt, "resolve_backends", _backends)
    monkeypatch.setattr(pt, "submit_or_resume", _submit)
    monkeypatch.setattr(pt, "_upload_file_id", _upload)
    monkeypatch.setattr(pt, "_deliver_image", _deliver)
    import core.services.storage as storage
    monkeypatch.setattr(storage, "rehost_remote", _rehost)


async def test_faceswap_no_backend_refunds(monkeypatch):
    _patch(monkeypatch, None)
    job_id = await _faceswap_job()
    await pt.process_faceswap_job(None, job_id)
    await _assert_failed_and_refunded(job_id, "provider not configured")


async def test_faceswap_provider_failure_refunds(monkeypatch):
    _patch(monkeypatch, _Backend(JobStatus("failed", error="boom")))
    job_id = await _faceswap_job()
    await pt.process_faceswap_job(None, job_id)
    await _assert_failed_and_refunded(job_id, "boom")


async def test_faceswap_timeout_refunds(monkeypatch):
    _patch(monkeypatch, _Backend(JobStatus("processing")))
    monkeypatch.setattr(pt, "MAX_POLLS", 1)
    job_id = await _faceswap_job()
    await pt.process_faceswap_job(None, job_id)
    await _assert_failed_and_refunded(job_id, "timeout")


async def test_faceswap_success_delivers(monkeypatch):
    delivered: list = []
    _patch(monkeypatch, _Backend(JobStatus("complete", result_url="https://x/r.jpg")),
           delivered=delivered)
    job_id = await _faceswap_job()
    await pt.process_faceswap_job(None, job_id)
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        assert job.status == "complete"
        assert job.result_url == "https://x/r.jpg"
        assert job.refunded_at is None
    assert delivered == ["https://x/r.jpg"]


async def test_faceswap_missing_input_refunds(monkeypatch):
    _patch(monkeypatch, _Backend(JobStatus("processing")))
    async with SessionFactory() as s:
        job = GenerationJob(user_id=1, service="faceswap", status="pending",
                            pack_type="image", cost_credits=1, params={"target": "t"})
        s.add(job)
        await s.commit()
        job_id = job.job_id
    await pt.process_faceswap_job(None, job_id)
    await _assert_failed_and_refunded(job_id, "missing input")
