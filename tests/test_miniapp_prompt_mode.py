"""Per-effect prompt policy (ТЗ §13): an effect's admin-set prompt_mode controls
the Mini App prompt field AND the backend enforces it —
  * required → empty prompt is rejected (400) before any charge;
  * hidden   → the user's text is ignored (can't smuggle an off-style prompt);
  * optional → unchanged (prompt used when present).
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException

from core.db import SessionFactory, engine
from core.models import Base, GenerationJob, MiniAppPhotoEffect, User


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _allow(monkeypatch):
    from core.services import moderation
    from core.services.moderation import ModerationResult

    async def _ok(_t: str) -> ModerationResult:
        return ModerationResult(True, "")

    monkeypatch.setattr(moderation, "moderate", _ok)


async def _seed(prompt_mode: str, template: str) -> int:
    async with SessionFactory() as s:
        s.add(User(user_id=1, language_code="ru", credits=10))
        e = MiniAppPhotoEffect(
            effect_id=1, category="all", name_ru="Style", enabled=True,
            recommended_model="nano_banana", prompt_template=template,
            prompt_mode=prompt_mode, max_photos=0,
        )
        s.add(e)
        await s.commit()
        return e.effect_id


async def test_required_prompt_rejects_empty():
    from api.routers import miniapp

    eid = await _seed("required", "{prompt}")
    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await miniapp.effect_generate(
                kind="photo", effect_id=eid, model="nano_banana",
                params="{}", prompt="   ", photos=[],
                tg={"id": 1, "username": "u", "language_code": "ru"}, session=s,
            )
        assert ei.value.status_code == 400


async def test_hidden_prompt_ignores_user_text(monkeypatch):
    from api.routers import miniapp

    _allow(monkeypatch)

    async def _noop(session, job, worker):
        return None

    monkeypatch.setattr(miniapp, "_enqueue_or_refund", _noop)

    eid = await _seed("hidden", "Apply Vintage style {prompt}")
    async with SessionFactory() as s:
        out = await miniapp.effect_generate(
            kind="photo", effect_id=eid, model="nano_banana",
            params="{}", prompt="ignore me please", photos=[],
            tg={"id": 1, "username": "u", "language_code": "ru"}, session=s,
        )
    assert out["status"] == "pending"
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, uuid.UUID(out["job_id"]))
        assert "ignore me" not in job.params["prompt"]      # user text dropped
        assert job.params["prompt"] == "Apply Vintage style"  # template kept


async def test_optional_prompt_uses_user_text(monkeypatch):
    from api.routers import miniapp

    _allow(monkeypatch)

    async def _noop(session, job, worker):
        return None

    monkeypatch.setattr(miniapp, "_enqueue_or_refund", _noop)

    eid = await _seed("optional", "{prompt}")
    async with SessionFactory() as s:
        out = await miniapp.effect_generate(
            kind="photo", effect_id=eid, model="nano_banana",
            params="{}", prompt="a neon cat", photos=[],
            tg={"id": 1, "username": "u", "language_code": "ru"}, session=s,
        )
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, uuid.UUID(out["job_id"]))
        assert job.params["prompt"] == "a neon cat"
