"""Contests / giveaways (ТЗ §7).

Service-level direct-call tests: create, idempotent entry, entry rejected when
closed, draw (N distinct winners + status flip), draw-twice rejection, and the
entrant count."""
from __future__ import annotations

import pytest
import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base
from core.models.contest import Contest, ContestEntry  # noqa: F401 — register tables
from core.services import contests


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_create():
    async with SessionFactory() as s:
        c = await contests.create(s, "Giveaway", "win stuff", winners_count=2)
        assert c.id is not None
        assert c.status == "open"
        assert c.winners_count == 2
        assert c.title == "Giveaway"


async def test_enter_is_idempotent():
    async with SessionFactory() as s:
        c = await contests.create(s, "G")
        cid = c.id
        first = await contests.enter(s, cid, user_id=10)
        second = await contests.enter(s, cid, user_id=10)
        assert first is True
        assert second is False
        assert await contests.entrants_count(s, cid) == 1


async def test_enter_rejected_when_closed():
    async with SessionFactory() as s:
        c = await contests.create(s, "G")
        await contests.close(s, c.id)
        with pytest.raises(contests.ContestError):
            await contests.enter(s, c.id, user_id=10)


async def test_entrants_count():
    async with SessionFactory() as s:
        c = await contests.create(s, "G")
        for uid in range(1, 6):
            await contests.enter(s, c.id, user_id=uid)
        assert await contests.entrants_count(s, c.id) == 5


async def test_draw_returns_distinct_winners_and_flips_status():
    async with SessionFactory() as s:
        c = await contests.create(s, "G", winners_count=3)
        cid = c.id
        entrants = list(range(100, 110))  # 10 entrants
        for uid in entrants:
            await contests.enter(s, cid, user_id=uid)

        winners = await contests.draw(s, cid)
        assert len(winners) == 3
        assert len(set(winners)) == 3  # distinct
        assert all(w in entrants for w in winners)  # actual entrants

    # Verify the PERSISTED state in a fresh session (the atomic claim commits the
    # status flip; the draw session's cached row is intentionally not synced).
    async with SessionFactory() as s:
        refreshed = await s.get(Contest, cid)
        assert refreshed.status == "drawn"
        assert refreshed.drawn_at is not None


async def test_draw_twice_rejected():
    async with SessionFactory() as s:
        c = await contests.create(s, "G")
        await contests.enter(s, c.id, user_id=1)
        await contests.draw(s, c.id)
        with pytest.raises(contests.ContestError):
            await contests.draw(s, c.id)


async def test_draw_rejects_when_drawn_concurrently():
    """A concurrent draw may flip the contest to 'drawn' after we load it. The
    atomic conditional UPDATE must reject the second draw (no second winner set /
    double-award), not just rely on a stale in-memory status check (TOCTOU)."""
    from sqlalchemy import update

    from core.models.contest import Contest as _Contest

    async with SessionFactory() as s:
        c = await contests.create(s, "G", winners_count=2)
        cid = c.id
        for uid in range(1, 6):
            await contests.enter(s, cid, user_id=uid)

    # Another actor draws first (flip status directly, as a concurrent claim would).
    async with SessionFactory() as s:
        await s.execute(update(_Contest).where(_Contest.id == cid).values(status="drawn"))
        await s.commit()

    # Our draw must now be rejected by the atomic claim.
    async with SessionFactory() as s:
        with pytest.raises(contests.ContestError):
            await contests.draw(s, cid)


async def test_draw_caps_at_entrant_count():
    async with SessionFactory() as s:
        c = await contests.create(s, "G", winners_count=5)
        await contests.enter(s, c.id, user_id=1)
        await contests.enter(s, c.id, user_id=2)
        winners = await contests.draw(s, c.id)
        assert len(winners) == 2  # fewer entrants than winners_count
