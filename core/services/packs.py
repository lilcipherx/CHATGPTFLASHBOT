"""Atomic pack-credit ledger (§8).

Credits live in pack_balances (image/video/music). Deduction is atomic via a
row-level lock (SELECT ... FOR UPDATE): check → deduct → commit, so concurrent
generations can't overspend. On provider failure the caller refunds.

Usage pattern in a handler:

    if not await try_consume(session, user, "image", cost):
        ...show Gate#2 top-up...
        return
    try:
        result = await provider.generate(...)
    except Exception:
        await refund(session, user, "image", cost)
        raise
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import PackBalance

PACK_FIELD = {
    "image": "image_credits",
    "video": "video_credits",
    "music": "music_credits",
}


def _field(pack: str) -> str:
    try:
        return PACK_FIELD[pack]
    except KeyError as exc:
        raise ValueError(f"unknown pack type {pack!r}") from exc


async def get_balance(session: AsyncSession, user_id: int, pack: str) -> int:
    field = _field(pack)
    balances = await session.get(PackBalance, user_id)
    return getattr(balances, field) if balances else 0


async def try_consume(
    session: AsyncSession, user_id: int, pack: str, amount: int, *, commit: bool = True
) -> bool:
    """Atomically deduct `amount` credits. Returns False (no change) if the
    balance is insufficient.

    ``commit=False`` keeps the deduction (and its row lock) in the caller's open
    transaction so the charge commits together with the work it pays for (e.g. the
    GenerationJob row) — a hard crash then leaves either both or neither, never a
    burned pack credit with no job."""
    # FIX: AUDIT13-M6 - reject non-positive amounts. Without this, a negative `amount`
    # makes `balance < amount` False (a non-negative balance is never < 0), so the code
    # falls through and subtracts a negative -> GRANTS pack credits. Mirrors the
    # credits.try_consume guard (AUDIT-9); this money-deduction sibling lacked it.
    if amount <= 0:
        return False
    field = _field(pack)
    row = (
        await session.execute(
            select(PackBalance).where(PackBalance.user_id == user_id).with_for_update()
        )
    ).scalar_one_or_none()
    # No balance row (or not enough) → nothing to consume. Return without a
    # session-wide rollback (which would discard the caller's other pending
    # changes) and without inserting a junk empty-balance row.
    if row is None or getattr(row, field) < amount:
        return False
    setattr(row, field, getattr(row, field) - amount)
    if commit:
        await session.commit()
    return True


async def refund(
    session: AsyncSession, user_id: int, pack: str, amount: int, *, commit: bool = True
) -> None:
    """Credit ``amount`` back to a pack balance. ``commit=False`` folds this into a
    larger atomic transaction the caller commits itself (e.g. promo redemption)."""
    # FIX: AUDIT13-M6 - never let a negative "refund" silently debit a balance.
    if amount <= 0:
        return
    field = _field(pack)
    row = (
        await session.execute(
            select(PackBalance).where(PackBalance.user_id == user_id).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        row = PackBalance(user_id=user_id, **{field: amount})
        session.add(row)
    else:
        setattr(row, field, getattr(row, field) + amount)
    if commit:
        await session.commit()
