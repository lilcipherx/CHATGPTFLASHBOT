"""Text-quota charge order + sponsored-free slots (Loop coverage): base weekly
allowance first, then ✨ balance, then QuotaExceeded; plus the admin-sponsored free
cap consume/refund. DB + fakeredis.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base
from core.services import quota
from core.services.credits import get_balance, grant
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_consume_text_uses_base_allowance_first():
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 3001)
        st = await quota.consume_text(s, user, cost=1)
        assert st.allowed and st.credits_charged == 0
        assert user.text_req_week == 1


async def test_consume_text_falls_back_to_credits():
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 3002)
        await grant(s, user, 5)
        # fresh week window + counter already at the ceiling → base allowance spent.
        # Commit so consume_text's `session.refresh(with_for_update)` re-reads these.
        user.week_start = datetime.now(UTC)
        user.text_req_week = 10**6
        await s.commit()
        st = await quota.consume_text(s, user, cost=1)
        assert st.allowed and st.credits_charged == 1
        assert await get_balance(s, 3002) == 4


async def test_consume_text_raises_when_exhausted():
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 3003)
        user.week_start = datetime.now(UTC)
        user.text_req_week = 10**6  # base spent, no credits
        await s.commit()
        with pytest.raises(quota.QuotaExceeded):
            await quota.consume_text(s, user, cost=1)


async def test_sponsored_free_consume_and_refund():
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 3004)
        # cap of 2 sponsored-free generations per day
        assert await quota.try_consume_sponsored_free(s, user, 2) is True
        assert await quota.try_consume_sponsored_free(s, user, 2) is True
        assert await quota.try_consume_sponsored_free(s, user, 2) is False  # cap hit
        assert quota.sponsored_free_remaining(user, 2) == 0
        # refunding returns a slot
        await quota.refund_sponsored(s, user)
        assert quota.sponsored_free_remaining(user, 2) == 1
