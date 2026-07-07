"""Support service (ТЗ §7): persist the support inbox + admin DMs.

Pure persistence — actually delivering an outbound message over Telegram is the
caller's job (admin endpoint / bot). These helpers only record the rows and run
the open-inbox / mark-handled queries.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.support import SupportMessage


async def record_inbound(session: AsyncSession, user_id: int, text: str) -> SupportMessage:
    """Store a user's /support message (unhandled, awaiting an admin reply)."""
    msg = SupportMessage(user_id=user_id, direction="in", text=text)
    session.add(msg)
    await session.commit()
    return msg


async def record_outbound(
    session: AsyncSession, user_id: int, admin_id: int, text: str
) -> SupportMessage:
    """Store an admin-to-user DM (a cold message or a reply)."""
    msg = SupportMessage(user_id=user_id, direction="out", admin_id=admin_id, text=text)
    session.add(msg)
    await session.commit()
    return msg


async def list_open(session: AsyncSession, limit: int = 50) -> list[SupportMessage]:
    """Open inbox: inbound, still-unhandled messages, newest first."""
    rows = (
        await session.scalars(
            select(SupportMessage)
            .where(SupportMessage.direction == "in", SupportMessage.handled.is_(False))
            .order_by(SupportMessage.created_at.desc())
            .limit(limit)
        )
    ).all()
    return list(rows)


async def mark_handled(session: AsyncSession, message_id: int) -> SupportMessage | None:
    """Flip an inbound message to handled. Returns the row (or None if missing)."""
    msg = await session.get(SupportMessage, message_id)
    if msg is None:
        return None
    msg.handled = True
    await session.commit()
    return msg
