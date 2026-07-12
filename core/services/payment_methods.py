"""Saved payment-method tokens for Premium auto-renewal (ТЗ §6).

A reusable token (YooKassa ``payment_method_id`` / Stripe ``payment_method`` +
customer) is captured at the original subscription checkout, persisted here from
the webhook apply path, and looked up by the auto-renewal cron to charge
off-session. One active row per (user, gateway): re-saving updates it in place.
"""
from __future__ import annotations

from sqlalchemy import select

# FIX: AUDIT-TEST - IntegrityError was used at save_method but never imported (NameError
# on the concurrent-insert path).
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import PaymentMethod
from core.payments.base import SavedMethod


async def save_method(
    session: AsyncSession,
    *,
    user_id: int,
    gateway: str,
    saved: SavedMethod,
    commit: bool = True,
) -> PaymentMethod:
    """Upsert the saved token for (user_id, gateway). Re-saving replaces the token /
    customer / card details and re-activates the row, so a user re-subscribing with a
    fresh card always renews against the latest method."""
    pm = await session.scalar(
        select(PaymentMethod).where(
            PaymentMethod.user_id == user_id,
            PaymentMethod.gateway == gateway,
        )
    )
    if pm is None:
        # FIX: AUDIT-TEST - populate the NOT NULL columns (token, is_active, …) at
        # construction, BEFORE flush. The old code inserted PaymentMethod(user_id,
        # gateway) with no token first → NOT NULL violation on `token` → IntegrityError
        # → the method was NEVER saved (auto-renewal had no vaulted token). Use a
        # SAVEPOINT (begin_nested) so a genuine (user,gateway) race rolls back only the
        # savepoint, not the caller's whole transaction.
        pm = PaymentMethod(
            user_id=user_id, gateway=gateway, token=saved.token,
            customer_id=saved.customer_id, brand=saved.brand,
            last4=saved.last4, is_active=True,
        )
        session.add(pm)
        try:
            async with session.begin_nested():
                await session.flush()
        except IntegrityError:
            # Lost the (user,gateway) race — the row now exists; update it below.
            pm = await session.scalar(
                select(PaymentMethod).where(
                    PaymentMethod.user_id == user_id,
                    PaymentMethod.gateway == gateway,
                )
            )
            if pm is None:
                return None
    pm.token = saved.token
    pm.customer_id = saved.customer_id
    pm.brand = saved.brand
    pm.last4 = saved.last4
    pm.is_active = True
    if commit:
        await session.commit()
        await session.refresh(pm)
    return pm


async def get_method(session: AsyncSession, user_id: int) -> PaymentMethod | None:
    """The user's active saved method to charge for auto-renewal, or None.

    If a user somehow has methods on multiple gateways, the most recently updated
    one wins (their latest subscription purchase)."""
    return await session.scalar(
        select(PaymentMethod)
        .where(
            PaymentMethod.user_id == user_id,
            PaymentMethod.is_active.is_(True),
        )
        .order_by(PaymentMethod.updated_at.desc(), PaymentMethod.id.desc())
        .limit(1)
    )


async def deactivate(session: AsyncSession, pm: PaymentMethod, *, commit: bool = True) -> None:
    """Soft-disable a method whose recurring charge was declined for a dead card, so
    the cron stops retrying it."""
    pm.is_active = False
    if commit:
        await session.commit()
