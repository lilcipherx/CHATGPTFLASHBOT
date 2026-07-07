"""Broadcast segment targeting (regression).

The premium/free segment filter must match User.is_premium exactly: a user whose
subscription EXPIRED still has sub_tier set (natural expiry never clears it), so a
sub_tier-only check would wrongly count them as premium and exclude them from the
free segment. We seed four users and assert each lands in the right bucket.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import select

from core.db import SessionFactory, engine
from core.models import Base, User
from workers.broadcast_tasks import _segment_filter


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _seg(segment: dict) -> set[int]:
    async with SessionFactory() as s:
        stmt = _segment_filter(select(User.user_id), segment)
        return set(await s.scalars(stmt))


async def _seed():
    now = datetime.now(UTC)
    async with SessionFactory() as s:
        s.add_all([
            # active premium
            User(user_id=1, sub_tier="premium", sub_expires=now + timedelta(days=10)),
            # EXPIRED premium — sub_tier still set, but no longer premium
            User(user_id=2, sub_tier="premium", sub_expires=now - timedelta(days=1)),
            # never subscribed
            User(user_id=3, sub_tier=None, sub_expires=None),
            # banned active premium — excluded from every segment
            User(user_id=4, sub_tier="premium", sub_expires=now + timedelta(days=10),
                 is_banned=True),
        ])
        await s.commit()


async def test_premium_segment_excludes_expired():
    await _seed()
    assert await _seg({"tier": "premium"}) == {1}  # only the active one


async def test_free_segment_includes_expired_premium():
    await _seed()
    # Expired premium (2) and never-subscribed (3); banned (4) excluded.
    assert await _seg({"tier": "free"}) == {2, 3}


async def test_all_segment_excludes_only_banned():
    await _seed()
    assert await _seg({}) == {1, 2, 3}
