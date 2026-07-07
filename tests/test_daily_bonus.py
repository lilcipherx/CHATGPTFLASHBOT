"""Daily login-streak bonus (core.services.daily_bonus).

Locks the critical idempotency property: a second claim the same UTC day must NOT
grant again (otherwise the bonus could be farmed infinitely), and the claim state
must persist across sessions. Real SQLite DB, no network.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, User
from core.services import daily_bonus
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_claim_once_per_day_and_persists():
    async with SessionFactory() as s:
        await get_or_create_user(s, 5001)

    async with SessionFactory() as s:
        u = await s.get(User, 5001)
        r1 = await daily_bonus.claim(s, u)
        assert r1.claimed and r1.streak == 1 and r1.amount > 0

    # Second claim the SAME day → refused, no extra credits.
    async with SessionFactory() as s:
        u = await s.get(User, 5001)
        credits_before = u.credits
        r2 = await daily_bonus.claim(s, u)
        assert not r2.claimed and r2.already_today
        assert u.credits == credits_before  # nothing granted

    # State persisted in a fresh session.
    async with SessionFactory() as s:
        u = await s.get(User, 5001)
        assert u.last_bonus_at is not None
        assert u.bonus_streak == 1


async def test_streak_grows_on_consecutive_day():
    async with SessionFactory() as s:
        await get_or_create_user(s, 5002)

    async with SessionFactory() as s:
        u = await s.get(User, 5002)
        await daily_bonus.claim(s, u)
        # Backdate the last claim to "yesterday" to simulate a consecutive day.
        u.last_bonus_at = datetime.now(UTC) - timedelta(days=1)
        await s.commit()

    async with SessionFactory() as s:
        u = await s.get(User, 5002)
        r = await daily_bonus.claim(s, u)
        assert r.claimed and r.streak == 2
