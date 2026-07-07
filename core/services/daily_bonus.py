"""Daily login-streak bonus (🪙 credits).

A user can claim once per UTC calendar day. Claiming on consecutive days grows the
streak (and the reward, up to a cap); missing a day resets the streak to 1. The
reward = base + step*(streak-1), clamped to cap. Amounts are admin-tunable via
config (daily_bonus_base / _step / _cap).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models import User


@dataclass
class BonusResult:
    claimed: bool          # False if already claimed today
    amount: int            # credits granted (0 when not claimed)
    streak: int            # current streak length
    already_today: bool = False


@dataclass
class BonusStatus:
    can_claim: bool        # True if today's bonus hasn't been claimed yet
    streak: int            # current streak length
    next_amount: int       # credits the user would receive by claiming now


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _reward_for(streak: int) -> int:
    raw = settings.daily_bonus_base + settings.daily_bonus_step * max(0, streak - 1)
    return max(0, min(settings.daily_bonus_cap, raw))


def _day(dt: datetime) -> datetime:
    """UTC calendar-day anchor (date at midnight) for comparing claim days."""
    return dt.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def status(user: User) -> BonusStatus:
    """Read-only: can the user claim today, and how much would they get?
    Mirrors claim()'s streak logic without mutating anything."""
    now = datetime.now(UTC)
    last = _aware(user.last_bonus_at)
    if last is not None and _day(last) == _day(now):
        return BonusStatus(False, user.bonus_streak, 0)
    if last is not None and (_day(now) - _day(last)).days == 1:
        next_streak = user.bonus_streak + 1
    else:
        next_streak = 1
    return BonusStatus(True, user.bonus_streak, _reward_for(next_streak))


async def claim(session: AsyncSession, user: User) -> BonusResult:
    """Claim today's bonus. Idempotent per day: a second call the same UTC day
    returns ``claimed=False, already_today=True`` and grants nothing."""
    await session.refresh(user, with_for_update=True)
    now = datetime.now(UTC)
    last = _aware(user.last_bonus_at)

    if last is not None and _day(last) == _day(now):
        await session.commit()
        return BonusResult(False, 0, user.bonus_streak, already_today=True)

    # Consecutive day → grow streak; gap (or first ever) → restart at 1.
    if last is not None and (_day(now) - _day(last)).days == 1:
        streak = user.bonus_streak + 1
    else:
        streak = 1

    amount = _reward_for(streak)
    # Credit + claim-state in ONE transaction. We must NOT call credits.grant here:
    # it does its own session.refresh(), which would discard the unsaved
    # last_bonus_at/bonus_streak below and let the bonus be farmed repeatedly.
    user.credits = max(0, user.credits + amount)
    user.bonus_streak = streak
    user.last_bonus_at = now
    await session.commit()
    return BonusResult(True, amount, streak)
