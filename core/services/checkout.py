"""Abandoned-cart tracking (ТЗ §7).

A ``CheckoutIntent`` row is recorded when a user reaches the pay step (Stars invoice
or external checkout) and flipped ``completed_at`` on a successful payment. The
engagement scheduler (core.services.notify) nudges still-open carts older than an
admin-set window, once each (``reminded_at``). All best-effort: a tracking hiccup must
never block a real checkout or payment.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import CheckoutIntent, User


async def record_intent(
    session: AsyncSession, user_id: int, *, kind: str, resume_cb: str,
    gateway: str, amount: int,
) -> None:
    """Record (or refresh) a purchase intent at the pay step. Re-tapping pay for the
    same product refreshes the existing OPEN cart's timer instead of piling up rows, so
    one cart yields at most one reminder. Best-effort — never raises into checkout."""
    try:
        now = datetime.now(UTC)
        existing = await session.scalar(
            select(CheckoutIntent).where(
                CheckoutIntent.user_id == user_id,
                CheckoutIntent.resume_cb == resume_cb,
                CheckoutIntent.completed_at.is_(None),
            ).limit(1)
        )
        if existing is not None:
            existing.created_at = now
            existing.reminded_at = None  # restart the reminder window
            existing.gateway = gateway
            existing.amount = amount
        else:
            session.add(CheckoutIntent(
                user_id=user_id, kind=kind, resume_cb=resume_cb,
                gateway=gateway, amount=amount, created_at=now,
            ))
        await session.commit()
    except Exception:  # noqa: BLE001 — cart tracking must never break a checkout
        await session.rollback()


async def mark_completed(session: AsyncSession, user_id: int) -> None:
    """Close all of a user's open carts after a successful payment, so a buyer is never
    nudged about an abandoned cart they just resolved. Best-effort."""
    try:
        await session.execute(
            update(CheckoutIntent)
            .where(CheckoutIntent.user_id == user_id, CheckoutIntent.completed_at.is_(None))
            .values(completed_at=datetime.now(UTC))
        )
        await session.commit()
    except Exception:  # noqa: BLE001
        await session.rollback()


async def abandoned(session: AsyncSession, after_hours: int) -> list[CheckoutIntent]:
    """Open carts older than ``after_hours`` that haven't been reminded yet, for users
    who aren't banned. ``after_hours`` is clamped to >= 0."""
    cutoff = datetime.now(UTC) - timedelta(hours=max(0, after_hours))
    rows = await session.scalars(
        select(CheckoutIntent)
        .join(User, User.user_id == CheckoutIntent.user_id)
        .where(
            CheckoutIntent.completed_at.is_(None),
            CheckoutIntent.reminded_at.is_(None),
            CheckoutIntent.created_at <= cutoff,
            User.is_banned.is_(False),
        )
        .order_by(CheckoutIntent.created_at)
    )
    return list(rows)
