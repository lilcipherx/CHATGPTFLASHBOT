"""The Mini App generate endpoints must charge (free slot / 🪙 credits) and insert
the GenerationJob in ONE transaction, so a hard crash between the two can never
burn a charge with no job to show for it.

These tests pin the observable invariant of that single-transaction design: a
failure anywhere before the atomic commit leaves the balance/slot completely
untouched (a rollback, not a compensating refund), and a success persists the
charge and the job together.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import HTTPException

from core.db import SessionFactory, engine
from core.models import (
    Base,
    GenerationJob,
    MiniAppPhotoEffect,
    MiniAppVideoEffect,
    User,
)


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


class _FakePhoto:
    """Minimal UploadFile stand-in — the endpoints only call .read()."""
    def __init__(self, data: bytes = b"\x89PNG\r\n"):
        self._data = data

    async def read(self) -> bytes:
        return self._data


async def _job_count(s) -> int:
    from sqlalchemy import func, select

    return await s.scalar(select(func.count()).select_from(GenerationJob))


def _allow(monkeypatch):
    """Make moderation pass so we exercise the charge path, not the content gate."""
    from core.services import moderation
    from core.services.moderation import ModerationResult

    async def _ok(_text: str) -> ModerationResult:
        return ModerationResult(True, "")

    monkeypatch.setattr(moderation, "moderate", _ok)


async def test_free_slot_and_job_commit_together(monkeypatch):
    # Success path: the free slot is consumed AND exactly one job exists — both
    # committed in the same transaction.
    from api.routers import miniapp

    _allow(monkeypatch)

    async def _noop_enqueue(session, job, worker):  # queue is covered elsewhere
        return None

    monkeypatch.setattr(miniapp, "_enqueue_or_refund", _noop_enqueue)

    async with SessionFactory() as s:
        s.add(User(user_id=1, language_code="ru", credits=0))
        eff = MiniAppPhotoEffect(
            name_ru="Test", category="all", enabled=True,
            recommended_model="nano_banana", max_photos=1,
        )
        s.add(eff)
        await s.commit()
        eid = eff.effect_id

    async with SessionFactory() as s:
        out = await miniapp.effect_generate(
            kind="photo", effect_id=eid, model="nano_banana",
            params="{}", prompt="a cat", photos=[],
            tg={"id": 1, "username": "u", "language_code": "ru"}, session=s,
        )
        assert out["status"] == "pending"

    async with SessionFactory() as s:
        u = await s.get(User, 1)
        assert u.mini_app_effects_week == 1          # free slot consumed
        assert await _job_count(s) == 1              # exactly one job, atomically


async def test_upload_failure_does_not_burn_free_slot(monkeypatch):
    # If storage fails after the (uncommitted) free-slot consume, a rollback must
    # leave the slot intact and create no job — no compensating refund needed.
    from api.routers import miniapp

    _allow(monkeypatch)
    monkeypatch.setattr(miniapp, "_validate_image", lambda _d: "png")

    async def _boom(*_a, **_k):
        raise RuntimeError("storage down")

    monkeypatch.setattr(miniapp.storage, "save_upload", _boom)

    async with SessionFactory() as s:
        s.add(User(user_id=2, language_code="ru", credits=0))
        eff = MiniAppPhotoEffect(
            name_ru="Test", category="all", enabled=True,
            recommended_model="nano_banana", max_photos=1,
        )
        s.add(eff)
        await s.commit()
        eid = eff.effect_id

    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await miniapp.effect_generate(
                kind="photo", effect_id=eid, model="nano_banana",
                params="{}", prompt="a cat", photos=[_FakePhoto()],
                tg={"id": 2, "username": "u", "language_code": "ru"}, session=s,
            )
        assert ei.value.status_code == 503

    async with SessionFactory() as s:
        u = await s.get(User, 2)
        assert u.mini_app_effects_week == 0          # slot NOT burned
        assert await _job_count(s) == 0


async def test_upload_failure_does_not_burn_credits(monkeypatch):
    # The unified VIDEO path always charges 🪙 (no free slot) — a storage failure
    # after the (uncommitted) deduction must roll the credits back and create no job.
    from api.routers import miniapp

    _allow(monkeypatch)
    monkeypatch.setattr(miniapp, "_validate_image", lambda _d: "png")

    async def _boom(*_a, **_k):
        raise RuntimeError("storage down")

    monkeypatch.setattr(miniapp.storage, "save_upload", _boom)

    async with SessionFactory() as s:
        s.add(User(user_id=3, language_code="ru", credits=50))
        eff = MiniAppVideoEffect(
            name_ru="Dance", category="all", enabled=True, provider="kling",
            recommended_model="kling_ai", max_photos=1,
        )
        s.add(eff)
        await s.commit()
        eid = eff.effect_id

    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await miniapp.effect_generate(
                kind="video", effect_id=eid, model="kling_ai",
                params="{}", prompt="a dance", photos=[_FakePhoto()],
                tg={"id": 3, "username": "u", "language_code": "ru"}, session=s,
            )
        assert ei.value.status_code == 503

    async with SessionFactory() as s:
        u = await s.get(User, 3)
        assert u.credits == 50                       # credits NOT burned
        assert await _job_count(s) == 0


async def test_double_submit_same_idempotency_key_is_deduped(monkeypatch):
    """U-3: a double-tap (the DOM Generate button and the Telegram MainButton both
    fire run()) carries ONE idempotency_key across both requests; the backend admits
    only the first and rejects the duplicate with 409 — exactly one job / one charge.
    Defense in depth behind the client's synchronous submitting-flag."""
    from api.routers import miniapp

    _allow(monkeypatch)

    async def _noop_enqueue(session, job, worker):
        return None

    monkeypatch.setattr(miniapp, "_enqueue_or_refund", _noop_enqueue)

    async with SessionFactory() as s:
        s.add(User(user_id=7, language_code="ru", credits=100))
        eff = MiniAppVideoEffect(
            name_ru="Dance", category="all", enabled=True, provider="kling",
            recommended_model="kling_ai", max_photos=1,
        )
        s.add(eff)
        await s.commit()
        eid = eff.effect_id

    kwargs = dict(
        kind="video", effect_id=eid, model="kling_ai", params="{}",
        prompt="a dance", photos=[], idempotency_key="tap-abc",
        tg={"id": 7, "username": "u", "language_code": "ru"},
    )

    async with SessionFactory() as s:
        out = await miniapp.effect_generate(session=s, **kwargs)
        assert out["status"] == "pending"

    # Double-tap twin (same idempotency_key) → rejected, no second job / charge.
    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await miniapp.effect_generate(session=s, **kwargs)
        assert ei.value.status_code == 409

    async with SessionFactory() as s:
        assert await _job_count(s) == 1              # exactly one job
        u = await s.get(User, 7)
        assert u.credits == 100 - out["cost"]        # charged exactly once


async def test_repeat_generation_with_different_key_is_allowed(monkeypatch):
    """The dedup keys on the CLIENT token, not request content, so a user genuinely
    re-generating the SAME effect+prompt (distinct submit → distinct idempotency_key)
    is NOT blocked — two jobs, charged twice. And a request with NO key (older client)
    is never deduped."""
    from api.routers import miniapp

    _allow(monkeypatch)

    async def _noop_enqueue(session, job, worker):
        return None

    monkeypatch.setattr(miniapp, "_enqueue_or_refund", _noop_enqueue)

    async with SessionFactory() as s:
        s.add(User(user_id=8, language_code="ru", credits=100))
        eff = MiniAppVideoEffect(
            name_ru="Dance", category="all", enabled=True, provider="kling",
            recommended_model="kling_ai", max_photos=1,
        )
        s.add(eff)
        await s.commit()
        eid = eff.effect_id

    def _kw(**extra):
        return dict(
            kind="video", effect_id=eid, model="kling_ai", params="{}",
            prompt="a dance", photos=[],
            tg={"id": 8, "username": "u", "language_code": "ru"}, **extra,
        )

    async with SessionFactory() as s:
        await miniapp.effect_generate(session=s, **_kw(idempotency_key="k1"))
    async with SessionFactory() as s:
        await miniapp.effect_generate(session=s, **_kw(idempotency_key="k2"))
    async with SessionFactory() as s:  # no key at all → never deduped
        await miniapp.effect_generate(session=s, **_kw())

    async with SessionFactory() as s:
        assert await _job_count(s) == 3              # all three admitted
