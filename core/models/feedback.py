"""User feedback on AI replies (ТЗ §7): 👍/👎 ratings + free-text complaints.

``MessageFeedback`` records a thumbs-up/down on a single AI reply (with a short
snippet of the rated text for context). ``Complaint`` is a free-text report filed
via /report that the admin panel can triage.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin
from core.models.types import BigIntPK


class MessageFeedback(Base, TimestampMixin):
    """A 👍/👎 vote on an AI reply."""

    __tablename__ = "message_feedback"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    # Telegram user id — 64-bit (ids have crossed 2^31; int4 overflows on Postgres).
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    rating: Mapped[str] = mapped_column(String(4))  # "up" | "down"
    # First ~200 chars of the rated message (context for the admin).
    snippet: Mapped[str | None] = mapped_column(String(200))


class Complaint(Base, TimestampMixin):
    """A free-text complaint filed via /report."""

    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    content: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
