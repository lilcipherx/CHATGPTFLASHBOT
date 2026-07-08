"""Support inbox + admin-to-user DMs (ТЗ §7).

A single ``SupportMessage`` row models both directions of the support channel:

* ``direction="in"``  — a user wrote to support via /support (``admin_id`` is NULL;
  ``handled`` flips True once an admin has replied / triaged it).
* ``direction="out"`` — an admin DM'd a user from the panel, either a cold message
  or a reply to an inbound one (``admin_id`` is the acting admin).

Keeping both directions in one table gives the admin a single chronological thread
per user and a trivial "open inbox" query (inbound + unhandled).
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin
from core.models.types import BigIntPK


class SupportMessage(Base, TimestampMixin):
    """One message in the support channel (inbound from a user or outbound from an admin)."""

    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    # Telegram user id — 64-bit (int4 overflows on Postgres for modern ids).
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    direction: Mapped[str] = mapped_column(String(3))  # "in" | "out"
    text: Mapped[str] = mapped_column(Text)
    # Set for outbound (the admin who sent it); NULL for inbound user messages.
    # FIX: AUDIT-15 - BigInteger to match AdminUser.id type
    admin_id: Mapped[int | None] = mapped_column(BigInteger)
    # Inbound only: flipped True once an admin has answered / triaged it.
    handled: Mapped[bool] = mapped_column(Boolean, default=False)
