"""Sponsored effects (is_ad), ТЗ §13: promoted (top of grid) + FREE for the user up
to an admin daily cap (the sponsor pays); past the cap the user pays as usual. The
free slot is refunded on a failed generation, and the displayed price is 0 while a
free slot remains.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, GenerationJob, MiniAppPhotoEffect, User
from core.services import pricing


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield


def _allow(monkeypatch):
    from core.services import moderation
    from core.services.moderation import ModerationResult

    async def _ok(_t: str) -> ModerationResult:
        return ModerationResult(True, "")

    monkeypatch.setattr(moderation, "moderate", _ok)


async def _set_cap(n: int):
    async with SessionFactory() as s:
        await pricing.set_config(s, {"sponsored_free_daily": n})


async def _seed(is_ad: bool = True, credits: int = 10, eid: int = 1, uid: int = 1,
                week_used: int = 0):
    from datetime import UTC, datetime

    async with SessionFactory() as s:
        # week_used pre-fills the free weekly slot so a photo effect falls through to
        # ✨ (a fresh user would otherwise generate free off the 25/week allowance).
        s.add(User(user_id=uid, language_code="ru", credits=credits,
                   mini_app_effects_week=week_used, mini_app_week_start=datetime.now(UTC)))
        s.add(MiniAppPhotoEffect(
            effect_id=eid, category="all", name_ru="Promo", enabled=True,
            recommended_model="nano_banana", prompt_template="{prompt}",
            max_photos=0, is_ad=is_ad,
        ))
        await s.commit()


async def _gen(monkeypatch, eid: int = 1, uid: int = 1):
    from api.routers import miniapp

    _allow(monkeypatch)

    async def _noop(session, job, worker):
        return None

    monkeypatch.setattr(miniapp, "_enqueue_or_refund", _noop)
    async with SessionFactory() as s:
        return await miniapp.effect_generate(
            kind="photo", effect_id=eid, model="nano_banana",
            params="{}", prompt="hello", photos=[],
            tg={"id": uid, "username": "u", "language_code": "ru"}, session=s,
        )


async def _user(uid: int = 1) -> User:
    async with SessionFactory() as s:
        return await s.get(User, uid)


async def test_sponsored_free_then_charges_past_cap(monkeypatch):
    await _set_cap(1)
    await _seed(is_ad=True, credits=10, week_used=25)   # weekly free slot exhausted

    out1 = await _gen(monkeypatch)
    assert out1["cost"] == 0                       # 1st sponsored gen is free
    u = await _user()
    assert u.credits == 10 and u.sponsored_free_day == 1

    out2 = await _gen(monkeypatch)
    assert out2["cost"] == 2                        # cap hit → normal nano_banana 1k cost
    u = await _user()
    assert u.credits == 8                           # charged ✨
    assert u.sponsored_free_day == 1                # counter not bumped on the paid one


async def test_non_sponsored_charges_normally(monkeypatch):
    await _set_cap(3)
    await _seed(is_ad=False, credits=10, week_used=25)   # weekly free slot exhausted
    out = await _gen(monkeypatch)
    assert out["cost"] == 2
    u = await _user()
    assert u.credits == 8 and u.sponsored_free_day == 0


async def test_effect_cost_is_zero_while_free_slot_remains(monkeypatch):
    from api.routers import miniapp
    from api.routers.miniapp import CostRequest

    await _set_cap(2)
    await _seed(is_ad=True, credits=0)
    async with SessionFactory() as s:
        out = await miniapp.effect_cost(
            kind="photo", effect_id=1, req=CostRequest(model="nano_banana", params={}),
            tg={"id": 1, "username": "u", "language_code": "ru"}, session=s,
        )
    assert out["cost"] == 0                          # sponsored + slot remaining → free

    # Exhaust the cap; the cost reverts to the real price.
    async with SessionFactory() as s:
        u = await s.get(User, 1)
        from datetime import UTC, datetime
        u.sponsored_free_day = 2
        u.sponsored_free_date = datetime.now(UTC)
        await s.commit()
    async with SessionFactory() as s:
        out = await miniapp.effect_cost(
            kind="photo", effect_id=1, req=CostRequest(model="nano_banana", params={}),
            tg={"id": 1, "username": "u", "language_code": "ru"}, session=s,
        )
    assert out["cost"] == 2


async def test_sponsored_effects_sorted_to_top(monkeypatch):
    from api.routers.miniapp import list_effects

    async with SessionFactory() as s:
        s.add(MiniAppPhotoEffect(effect_id=1, category="all", name_ru="Normal",
                                 enabled=True, is_ad=False, sort_order=0))
        s.add(MiniAppPhotoEffect(effect_id=2, category="all", name_ru="Sponsored",
                                 enabled=True, is_ad=True, sort_order=10))
        await s.commit()
    async with SessionFactory() as s:
        out = await list_effects(kind="photo", trending=False, category="all",
                                 tg={"id": 1, "username": "u", "language_code": "ru"}, session=s)
    assert out[0]["id"] == 2                          # sponsored first despite higher sort_order


async def test_failed_job_refunds_sponsored_slot():
    from core.services.refunds import refund_job

    async with SessionFactory() as s:
        from datetime import UTC, datetime
        s.add(User(user_id=1, language_code="ru", credits=0,
                   sponsored_free_day=1, sponsored_free_date=datetime.now(UTC)))
        job = GenerationJob(
            user_id=1, service="photoeffect", model_variant="nano_banana",
            params={"sponsored_free": True, "preset_id": 1}, cost_credits=0,
            pack_type=None, status="failed",
        )
        s.add(job)
        await s.commit()
        jid = job.job_id

    async with SessionFactory() as s:
        job = await s.get(GenerationJob, jid)
        await refund_job(s, job)
    async with SessionFactory() as s:
        u = await s.get(User, 1)
        assert u.sponsored_free_day == 0             # free slot returned
