"""🪙 Credits — the Mini App's own currency (separate from image/video/music
packs). Used for Фотоэффекты / Видеоэффекты once the weekly free quota is spent
(§23F). Deduction is atomic via a row-level lock so concurrent generations can't
overspend; the caller refunds on provider failure.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User


async def get_balance(session: AsyncSession, user_id: int) -> int:
    user = await session.get(User, user_id)
    return user.credits if user else 0


async def try_consume(
    session: AsyncSession, user: User, amount: int, *, commit: bool = True
) -> bool:
    """Atomically deduct `amount` 🪙. Returns False (no change) if insufficient.

    ``commit=False`` keeps the deduction (and its row lock) in the caller's open
    transaction so it can commit the charge together with the work it pays for
    (e.g. the GenerationJob row) — a hard crash then leaves either both or neither,
    never a burned credit with no job."""
    # FIX: AUDIT-9 - reject non-positive amounts (would grant credits instead of consuming)
    if amount <= 0:
        return False
    await session.refresh(user, with_for_update=True)
    if user.credits < amount:
        return False
    user.credits -= amount
    if commit:
        await session.commit()
    return True


async def grant(
    session: AsyncSession, user: User, amount: int, *, commit: bool = True
) -> None:
    """Add 🪙 (top-up, refund, or admin grant). Never goes below zero.

    ``commit=False`` lets a caller fold this grant into a larger atomic
    transaction it commits itself (e.g. promo redemption), instead of releasing
    any locks here mid-operation."""
    # FIX: AUDIT13-L7 - `grant` must never be usable to DEBIT. A negative amount would
    # slip past `max(0, ...)` (which only floors the result) and silently reduce the
    # balance. Callers already clamp, but guard defensively at the primitive.
    if amount <= 0:
        return
    await session.refresh(user, with_for_update=True)
    user.credits = max(0, user.credits + amount)
    if commit:
        await session.commit()
