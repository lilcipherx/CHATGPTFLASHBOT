"""Multi-variant image generation (ТЗ §5): cost scales with the requested count,
and variants the provider fails to return are refunded."""
from __future__ import annotations

import pytest_asyncio

import bot.handlers.photo as photo
from core.ai_router.base import ImageResult
from core.ai_router.image_specs import PHOTO_SPECS
from core.db import SessionFactory, engine
from core.models import Base, PackBalance
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


class _Msg:
    """Minimal async Message stand-in for _run_photo."""
    def __init__(self):
        self.photos: list = []

    async def answer(self, *a, **k):
        return self  # the "please wait" message reuses this stub

    async def edit_text(self, *a, **k):
        return self

    async def delete(self):
        return None

    async def answer_photo(self, *a, **k):
        self.photos.append(a)


class _State:
    def __init__(self):
        self.data: dict = {}

    async def update_data(self, **kw):
        self.data.update(kw)


async def _balance(session, uid: int) -> int:
    b = await session.get(PackBalance, uid)
    return b.image_credits if b else 0


async def test_charges_for_all_variants(monkeypatch):
    async def fake_gen(service_key, prompt, cfg):
        return [ImageResult(url=f"u{i}") for i in range(int(cfg.get("count", 1)))]
    monkeypatch.setattr(photo, "generate_image", fake_gen)

    spec = PHOTO_SPECS["seedream"]  # pack=image, cost=1 per image
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 8001)
        bal = await s.get(PackBalance, user.user_id)
        bal.image_credits = 10
        await s.commit()

        await photo._run_photo(_Msg(), _State(), s, user, spec,
                               {"count": 3}, "cat", lambda k, **kw: k)
        # 3 variants × cost 1 = 3 charged from the image pack.
        assert await _balance(s, user.user_id) == 7


async def test_refunds_undelivered_variants(monkeypatch):
    async def fake_gen(service_key, prompt, cfg):
        return [ImageResult(url="only-one")]  # provider returns 1 of 3
    monkeypatch.setattr(photo, "generate_image", fake_gen)

    spec = PHOTO_SPECS["seedream"]
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 8002)
        bal = await s.get(PackBalance, user.user_id)
        bal.image_credits = 10
        await s.commit()

        await photo._run_photo(_Msg(), _State(), s, user, spec,
                               {"count": 3}, "dog", lambda k, **kw: k)
        # charged 3, refunded 2 undelivered → net 1 spent.
        assert await _balance(s, user.user_id) == 9
