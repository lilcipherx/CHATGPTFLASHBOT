"""Free model-choice endpoints (§ variant 3): the user picks a VIDEO_SPECS /
PHOTO_SPECS model directly instead of a curated preset. These mirror the effect
generate invariants — atomic charge+job, History inclusion — without a preset row.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, GenerationJob, User


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _allow(monkeypatch):
    from core.services import moderation
    from core.services.moderation import ModerationResult

    async def _ok(_text: str):
        return ModerationResult(True, "")

    monkeypatch.setattr(moderation, "moderate", _ok)


async def _job_count(s) -> int:
    from sqlalchemy import func, select
    return await s.scalar(select(func.count()).select_from(GenerationJob))


async def test_free_models_list_and_cost():
    from api.routers import miniapp

    async with SessionFactory() as s:
        s.add(User(user_id=1, language_code="ru", credits=0))
        await s.commit()

    async with SessionFactory() as s:
        vids = await miniapp.free_models("video", tg={"id": 1}, session=s)
        keys = {m["key"] for m in vids}
        assert "kling_ai" in keys and "veo" in keys
        # each entry carries a settings card + a positive base price
        one = next(m for m in vids if m["key"] == "kling_ai")
        assert one["card"]["key"] == "kling_ai" and one["price"] >= 1

        photos = await miniapp.free_models("photo", tg={"id": 1}, session=s)
        assert "nano_banana" in {m["key"] for m in photos}

        cost = await miniapp.free_model_cost(
            "video", "kling_ai", miniapp.ParamsRequest(params={}), tg={"id": 1}, session=s,
        )
        assert cost["cost"] >= 1 and cost["currency"] == "credits"


async def test_free_model_generate_charges_and_creates_job(monkeypatch):
    from api.routers import miniapp

    _allow(monkeypatch)

    async def _noop_enqueue(session, job, worker):
        return None
    monkeypatch.setattr(miniapp, "_enqueue_or_refund", _noop_enqueue)

    async with SessionFactory() as s:
        s.add(User(user_id=2, language_code="ru", credits=50))
        await s.commit()

    async with SessionFactory() as s:
        out = await miniapp.free_model_generate(
            kind="video", model="kling_ai", params="{}", prompt="a neon city",
            photos=[], tg={"id": 2, "username": "u", "language_code": "ru"}, session=s,
        )
        assert out["status"] == "pending" and out["cost"] >= 1
        cost = out["cost"]

    async with SessionFactory() as s:
        u = await s.get(User, 2)
        assert u.credits == 50 - cost                 # charged the model's price
        assert await _job_count(s) == 1
        from sqlalchemy import select
        job = await s.scalar(select(GenerationJob))
        assert job.service == "kling_ai"              # unified path routes by model key
        assert job.model_variant == "kling_ai"
        assert job.params["free_model"] == "kling_ai"
        assert "preset_id" not in job.params


async def test_free_model_generate_insufficient_credits(monkeypatch):
    from fastapi import HTTPException

    from api.routers import miniapp

    _allow(monkeypatch)

    async with SessionFactory() as s:
        s.add(User(user_id=3, language_code="ru", credits=0))
        await s.commit()

    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await miniapp.free_model_generate(
                kind="video", model="kling_ai", params="{}", prompt="x",
                photos=[], tg={"id": 3, "username": "u", "language_code": "ru"}, session=s,
            )
        assert ei.value.status_code == 402
    async with SessionFactory() as s:
        assert await _job_count(s) == 0               # nothing charged, no job


async def test_free_model_job_appears_in_history(monkeypatch):
    from api.routers import miniapp

    _allow(monkeypatch)

    async def _noop_enqueue(session, job, worker):
        return None
    monkeypatch.setattr(miniapp, "_enqueue_or_refund", _noop_enqueue)

    async with SessionFactory() as s:
        s.add(User(user_id=4, language_code="ru", credits=50))
        await s.commit()

    async with SessionFactory() as s:
        await miniapp.free_model_generate(
            kind="video", model="veo", params="{}", prompt="clouds",
            photos=[], tg={"id": 4, "username": "u", "language_code": "ru"}, session=s,
        )

    async with SessionFactory() as s:
        hist = await miniapp.jobs_history(tg={"id": 4}, session=s)
        assert len(hist) == 1
        assert hist[0]["kind"] == "video"
        assert hist[0]["model"] == "veo"             # replayable by model
        assert hist[0]["preset_id"] is None


async def test_unknown_free_model_404():
    from fastapi import HTTPException

    from api.routers import miniapp

    async with SessionFactory() as s:
        s.add(User(user_id=5, language_code="ru", credits=10))
        await s.commit()

    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await miniapp.free_model_cost(
                "video", "does_not_exist", miniapp.ParamsRequest(params={}),
                tg={"id": 5}, session=s,
            )
        assert ei.value.status_code == 404
