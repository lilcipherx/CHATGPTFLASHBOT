"""Mini App History (/jobs) must list video effects too (ТЗ §13).

Regression: the live UI generates effects through the unified Higgsfield endpoint,
which stores a VIDEO_SPECS key (e.g. "kling_ai") as the job's ``service`` so the
worker can route the provider by it. The History query filtered ``service ==
'videoeffect'`` only, so every video effect silently vanished from History and any
that slipped through was mislabeled "photo". History now matches on the stable
``preset_id`` marker every Mini App effect job carries, and derives kind from
whether the service is the shared "photoeffect" one.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, GenerationJob


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _add(uid: int, service: str, params: dict) -> str:
    async with SessionFactory() as s:
        job = GenerationJob(
            user_id=uid, service=service, model_variant=service,
            params=params, status="complete", result_url="https://x/r.mp4",
        )
        s.add(job)
        await s.commit()
        return str(job.job_id)


async def _history(uid: int = 1) -> list[dict]:
    from api.routers.miniapp import jobs_history

    async with SessionFactory() as s:
        return await jobs_history(
            tg={"id": uid, "username": "u", "language_code": "ru"}, session=s
        )


async def test_unified_video_effect_appears_as_video():
    # Unified path: service is the model key, preset_id marks it a Mini App effect.
    await _add(1, "kling_ai", {"preset_id": 7, "prompt": "x"})
    out = await _history()
    assert len(out) == 1
    assert out[0]["kind"] == "video"          # was wrongly "photo" before the fix
    assert out[0]["preset_id"] == 7           # exposed so History can offer "повторить"


async def test_photo_effect_appears_as_photo():
    await _add(1, "photoeffect", {"preset_id": 3})
    out = await _history()
    assert len(out) == 1
    assert out[0]["kind"] == "photo"


async def test_legacy_videoeffect_still_listed():
    await _add(1, "videoeffect", {"effect": "boom"})
    out = await _history()
    assert len(out) == 1
    assert out[0]["kind"] == "video"


async def test_bot_generation_without_preset_is_excluded():
    # A non-Mini-App video job (same service key, no preset_id) must NOT leak in.
    await _add(1, "kling_ai", {"prompt": "from the bot"})
    out = await _history()
    assert out == []


async def test_only_own_jobs():
    await _add(1, "photoeffect", {"preset_id": 1})
    await _add(2, "photoeffect", {"preset_id": 2})
    assert len(await _history(1)) == 1
