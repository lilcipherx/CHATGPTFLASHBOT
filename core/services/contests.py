"""Contest / giveaway service (ТЗ §7).

An admin creates a contest; users enter once each (entry is idempotent — the
unique (contest_id, user_id) constraint makes a duplicate a no-op); the admin
draws ``winners_count`` random distinct entrants and the contest flips to
``drawn`` exactly once."""
from __future__ import annotations

import random

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User
from core.models.contest import Contest, ContestEntry
from core.services import credits, packs

# Prize vocabulary shared with promo codes (core.services.promos): a "credits"
# prize tops up ✨; the rest are generation-pack grants.
_PACK_PRIZES = {"image", "video", "music"}
PRIZE_TYPES = {"credits", *_PACK_PRIZES}


class ContestError(Exception):
    """A contest operation was rejected (not open / already drawn / missing)."""


def _clean_prize(prize_type: str | None, prize_amount: int | None) -> tuple[str, int]:
    """Normalise prize fields: a known type and a non-negative amount. An unknown
    type or amount <= 0 collapses to the notify-only default (credits / 0)."""
    ptype = (prize_type or "credits").strip().lower()
    if ptype not in PRIZE_TYPES:
        ptype = "credits"
    amount = max(0, int(prize_amount or 0))
    return ptype, amount


async def create(
    session: AsyncSession,
    title: str,
    description: str | None = None,
    winners_count: int = 1,
    prize_type: str = "credits",
    prize_amount: int = 0,
) -> Contest:
    """Create an open contest, optionally with an auto-prize (prize_amount > 0)."""
    ptype, amount = _clean_prize(prize_type, prize_amount)
    contest = Contest(
        title=title,
        description=description,
        winners_count=max(1, winners_count),
        prize_type=ptype,
        prize_amount=amount,
        status="open",
    )
    session.add(contest)
    await session.commit()
    await session.refresh(contest)
    return contest


async def enter(session: AsyncSession, contest_id: int, user_id: int) -> bool:
    """Register ``user_id`` for the contest. Idempotent: a second entry is a no-op
    (returns False). Returns True when a new entry was created. Raises ContestError
    if the contest is missing or not open."""
    contest = await session.get(Contest, contest_id)
    if contest is None:
        raise ContestError("contest not found")
    if contest.status != "open":
        raise ContestError("contest is not open")

    # Fast path: already entered (avoids a constraint violation + rollback, which
    # would expire the caller's loaded objects).
    existing = await session.scalar(
        select(ContestEntry.id)
        .where(ContestEntry.contest_id == contest_id)
        .where(ContestEntry.user_id == user_id)
    )
    if existing is not None:
        return False

    entry = ContestEntry(contest_id=contest_id, user_id=user_id)
    session.add(entry)
    try:
        await session.commit()
    except IntegrityError:
        # Lost a race on the unique constraint — already entered.
        await session.rollback()
        return False
    return True


async def list_open(session: AsyncSession) -> list[Contest]:
    """Open contests, newest first."""
    rows = await session.scalars(
        select(Contest)
        .where(Contest.status == "open")
        .order_by(Contest.created_at.desc(), Contest.id.desc())
    )
    return list(rows.all())


async def list_all(session: AsyncSession) -> list[Contest]:
    """All contests, newest first (admin view)."""
    rows = await session.scalars(
        select(Contest).order_by(Contest.created_at.desc(), Contest.id.desc())
    )
    return list(rows.all())


async def entrants_count(session: AsyncSession, contest_id: int) -> int:
    """Number of distinct entrants for a contest."""
    n = await session.scalar(
        select(func.count()).select_from(ContestEntry)
        .where(ContestEntry.contest_id == contest_id)
    )
    return int(n or 0)


async def close(session: AsyncSession, contest_id: int) -> Contest:
    """Stop accepting entries (open -> closed). No-op effect if already closed.
    Raises ContestError if missing or already drawn."""
    contest = await session.get(Contest, contest_id)
    if contest is None:
        raise ContestError("contest not found")
    if contest.status == "drawn":
        raise ContestError("contest already drawn")
    contest.status = "closed"
    await session.commit()
    await session.refresh(contest)
    return contest


async def draw(session: AsyncSession, contest_id: int, *, commit: bool = True) -> list[int]:
    """Pick up to ``winners_count`` random distinct entrants, flip status to drawn
    (with drawn_at), and return the winner user_ids. Raises ContestError if the
    contest is missing or has already been drawn.

    FIX: AUDIT12-16 - add commit=False so callers can fold prize grants + audit
    into one atomic transaction (was: draw() committed internally)."""

    contest = await session.get(Contest, contest_id)
    if contest is None:
        raise ContestError("contest not found")
    # Read fields BEFORE the bulk UPDATE below — that UPDATE expires the in-memory
    # row, and accessing an expired attribute afterwards would trigger a lazy reload
    # outside the async context.
    winners_count = contest.winners_count
    prize_type, prize_amount = _clean_prize(contest.prize_type, contest.prize_amount)

    # Atomically CLAIM the draw: only the transaction whose UPDATE still matches a
    # not-yet-drawn contest wins, so two concurrent draws (admin double-click / two
    # admins) can never both select winners and double-award. A plain
    # check-status-then-set was a TOCTOU race (both pass the check, both draw).
    claimed = await session.execute(
        update(Contest)
        .where(Contest.id == contest_id, Contest.status != "drawn")
        .values(status="drawn", drawn_at=func.now())
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount == 0:
        await session.rollback()
        raise ContestError("contest already drawn")

    rows = await session.scalars(
        select(ContestEntry.user_id).where(ContestEntry.contest_id == contest_id)
    )
    entrants = list(rows.all())
    k = min(winners_count, len(entrants))
    winners = random.sample(entrants, k) if k > 0 else []

    # Grant the auto-prize to each winner in THIS transaction (commit=False) so the
    # award lands atomically with the draw claim — the claim guarantees draw runs at
    # most once, so winners can never be double-paid. prize_amount == 0 is notify-only.
    if prize_amount > 0:
        for uid in winners:
            await _grant_prize(session, uid, prize_type, prize_amount)

    # FIX: AUDIT12-16 - honor commit=False so callers can fold audit into this tx
    if commit:
        await session.commit()
    return winners


async def _grant_prize(
    session: AsyncSession, user_id: int, prize_type: str, amount: int
) -> None:
    """Award one winner their prize, folded into the caller's transaction. A credits
    prize tops up ✨ (skipped if the winner has no User row); pack prizes credit the
    matching generation pack."""
    if prize_type in _PACK_PRIZES:
        await packs.refund(session, user_id, prize_type, amount, commit=False)
        return
    user = await session.get(User, user_id)
    if user is None:
        # FIX: AUDIT-127 - log when prize can't be granted (user deleted)
        import structlog
        # FIX: AUDIT-TEST - `contest_id` isn't in this function's scope (params are
        # user_id/prize_type/amount) → NameError crashed the whole draw when a winner
        # had been deleted. Log what we actually have.
        structlog.get_logger().warning(
            "contests.prize_skipped_no_user", user_id=user_id, prize_type=prize_type
        )
        return
    await credits.grant(session, user, amount, commit=False)
