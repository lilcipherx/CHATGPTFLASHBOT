"""Live admin-editable pricing for Face Swap / Upscale (ТЗ §5/§8).

The bot's faceswap/upscale charge now reads the `phototools` live-config block
(admin-editable), falling back to the historic hardcoded tariffs.
"""
from __future__ import annotations

import pytest_asyncio

import bot.handlers.photo as photo
from core.db import SessionFactory, engine
from core.models import Base, PackBalance
from core.services import pricing
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_costs_default_without_override():
    async with SessionFactory() as s:
        assert await photo._faceswap_cost(s) == 1
        assert await photo._upscale_cost(s, "x2") == 2
        assert await photo._upscale_cost(s, "x4") == 4


async def test_costs_follow_admin_override():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"phototools": {
            "face_swap": 5, "upscale_x2": 7, "upscale_x4": 11,
        }})
        assert await photo._faceswap_cost(s) == 5
        assert await photo._upscale_cost(s, "x2") == 7
        assert await photo._upscale_cost(s, "x4") == 11


async def test_garbage_override_falls_back():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"phototools": {"face_swap": "abc"}})
        assert await photo._faceswap_cost(s) == 1  # bad value → default


class _Msg:
    def __init__(self):
        self.photo = [type("P", (), {"file_id": "f1"})()]

    async def answer(self, *a, **k):
        return self


class _State:
    def __init__(self, **data):
        self.data = data

    async def get_data(self):
        return self.data

    async def clear(self):
        self.data = {}

    async def set_state(self, *_a, **_k):
        return None

    async def update_data(self, **kw):
        self.data.update(kw)


async def test_upscale_charges_live_price(monkeypatch):
    async def noop_enqueue(session, job, task):
        return None
    monkeypatch.setattr(photo, "enqueue_or_refund", noop_enqueue)

    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 9100)
        bal = await s.get(PackBalance, user.user_id)
        bal.image_credits = 20
        await s.commit()
        await pricing.set_config(s, {"phototools": {"upscale_x4": 9}})

        await photo.upscale_image(
            _Msg(), _State(factor="x4"), s, user, lambda k, **kw: k
        )
        bal = await s.get(PackBalance, user.user_id)
        assert bal.image_credits == 11  # 20 − 9 (live X4 price)
