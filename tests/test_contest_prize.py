"""Contest auto-prize (ТЗ §7): drawing winners grants the admin-set prize
automatically — ✨ credits or a generation pack — instead of the admin topping up
each winner by hand. A prize_amount of 0 is notify-only (unchanged behaviour), and
because the draw can only be claimed once, winners are never double-paid.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, PackBalance, User
from core.models.contest import Contest, ContestEntry  # noqa: F401 — register tables
from core.services import contests


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _seed_users(uids: list[int], *, credits: int = 0) -> None:
    async with SessionFactory() as s:
        for uid in uids:
            s.add(User(user_id=uid, language_code="ru", credits=credits))
        await s.commit()


async def test_credits_prize_granted_to_all_winners():
    uids = [101, 102, 103]
    await _seed_users(uids, credits=10)
    async with SessionFactory() as s:
        c = await contests.create(
            s, "G", winners_count=3, prize_type="credits", prize_amount=50
        )
        for uid in uids:
            await contests.enter(s, c.id, uid)
        winners = await contests.draw(s, c.id)
    assert set(winners) == set(uids)
    async with SessionFactory() as s:
        for uid in uids:
            u = await s.get(User, uid)
            assert u.credits == 60  # 10 + 50 prize


async def test_pack_prize_credited_to_winner_balance():
    await _seed_users([201])
    async with SessionFactory() as s:
        c = await contests.create(
            s, "G", winners_count=1, prize_type="video", prize_amount=5
        )
        await contests.enter(s, c.id, 201)
        await contests.draw(s, c.id)
    async with SessionFactory() as s:
        bal = await s.get(PackBalance, 201)
        assert bal is not None
        assert bal.video_credits == 5


async def test_zero_amount_is_notify_only_no_grant():
    await _seed_users([301], credits=10)
    async with SessionFactory() as s:
        c = await contests.create(
            s, "G", winners_count=1, prize_type="credits", prize_amount=0
        )
        await contests.enter(s, c.id, 301)
        await contests.draw(s, c.id)
    async with SessionFactory() as s:
        u = await s.get(User, 301)
        assert u.credits == 10  # unchanged


async def test_unknown_prize_type_falls_back_to_credits():
    async with SessionFactory() as s:
        c = await contests.create(
            s, "G", prize_type="bogus", prize_amount=-5
        )
    async with SessionFactory() as s:
        refreshed = await s.get(Contest, c.id)
        assert refreshed.prize_type == "credits"
        assert refreshed.prize_amount == 0  # negative clamped to 0


async def test_missing_winner_user_row_does_not_crash_draw():
    # A credits prize for an entrant with no User row is simply skipped (no crash).
    async with SessionFactory() as s:
        c = await contests.create(
            s, "G", winners_count=1, prize_type="credits", prize_amount=50
        )
        await contests.enter(s, c.id, 999)  # never seeded as a User
        winners = await contests.draw(s, c.id)
    assert winners == [999]
