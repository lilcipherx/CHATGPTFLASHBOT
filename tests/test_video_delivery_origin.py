"""Video delivery is origin-aware (ТЗ §13). The video worker is shared by the bot
and the Mini App:

* Mini App video EFFECTS (params carry a preset_id) have an in-app result + History,
  so a chat-send failure must NOT discard/refund an already generated+paid video —
  the job is finalised 'complete' and the result_url stays pollable.
* Bot video generations have no in-app fallback, so a chat-send failure refunds +
  fails (never charge for a video never received).
"""
from __future__ import annotations

import pytest_asyncio

import workers.video_tasks as vt
from core.db import SessionFactory, engine
from core.models import Base, GenerationJob, User


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionFactory() as s:
        s.add(User(user_id=1, language_code="ru"))
        await s.commit()
    yield


async def _seed_job(params: dict):
    async with SessionFactory() as s:
        job = GenerationJob(
            user_id=1, service="kling_ai", model_variant="kling_ai",
            params=params, status="processing", cost_credits=0, pack_type=None,
        )
        s.add(job)
        await s.commit()
        return job.job_id  # uuid.UUID — valid PK for SQLite + Postgres


async def _get(job_id) -> GenerationJob:
    async with SessionFactory() as s:
        return await s.get(GenerationJob, job_id)


async def _fail_deliver(*_a, **_k):
    raise RuntimeError("telegram can't fetch the url")


async def test_miniapp_video_keeps_result_when_chat_send_fails(monkeypatch):
    monkeypatch.setattr(vt, "_deliver", _fail_deliver)
    job_id = await _seed_job({"preset_id": 5})           # Mini App effect
    await vt._deliver_and_finalise(job_id, "https://x/v.mp4")
    job = await _get(job_id)
    assert job.status == "complete"                       # not refunded/failed
    assert job.result_url == "https://x/v.mp4"            # stays pollable in-app


async def test_bot_video_refunds_when_chat_send_fails(monkeypatch):
    monkeypatch.setattr(vt, "_deliver", _fail_deliver)
    job_id = await _seed_job({"prompt": "from the bot"})  # no preset_id → bot job
    await vt._deliver_and_finalise(job_id, "https://x/v.mp4")
    job = await _get(job_id)
    assert job.status == "failed"                         # chat is the only channel
    assert job.error and "deliver" in job.error


async def test_successful_send_finalises_either_origin(monkeypatch):
    sent: list[str] = []

    async def _ok_deliver(job, url, locale):
        sent.append(url)

    monkeypatch.setattr(vt, "_deliver", _ok_deliver)
    job_id = await _seed_job({"preset_id": 9})
    await vt._deliver_and_finalise(job_id, "https://x/ok.mp4")
    job = await _get(job_id)
    assert job.status == "complete"
    assert sent == ["https://x/ok.mp4"]                   # bonus chat send happened


async def test_already_complete_is_noop(monkeypatch):
    calls: list[str] = []

    async def _spy_deliver(job, url, locale):
        calls.append(url)

    monkeypatch.setattr(vt, "_deliver", _spy_deliver)
    job_id = await _seed_job({"preset_id": 1})
    async with SessionFactory() as s:                     # pre-mark complete
        job = await s.get(GenerationJob, job_id)
        job.status = "complete"
        await s.commit()
    await vt._deliver_and_finalise(job_id, "https://x/v.mp4")
    assert calls == []                                    # no double send
