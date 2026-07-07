"""Giveaways / contests (ТЗ §7).

An admin creates a Contest; users enter once each via the bot; the admin later
draws a fixed number of random distinct winners. ``ContestEntry`` carries a
unique (contest_id, user_id) constraint so a user can only enter a contest once —
this is the single source of truth for entry idempotency."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin
from core.models.types import BigIntPK


class Contest(Base, TimestampMixin):
    """One giveaway. status: open (accepting entries) | closed | drawn."""

    __tablename__ = "contests"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open|closed|drawn
    winners_count: Mapped[int] = mapped_column(Integer, default=1)
    # Auto-prize granted to each winner on draw. prize_type mirrors the promo reward
    # vocabulary (credits | image | video | music); prize_amount == 0 means no
    # auto-prize (notify-only — the admin grants manually).
    prize_type: Mapped[str] = mapped_column(String(12), default="credits")
    prize_amount: Mapped[int] = mapped_column(Integer, default=0)
    drawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContestEntry(Base, TimestampMixin):
    """A single user's entry into a contest. One row per (contest, user)."""

    __tablename__ = "contest_entries"
    # One entry per user per contest — the DB guards against double entry.
    __table_args__ = (UniqueConstraint("contest_id", "user_id", name="uq_contest_entry"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    contest_id: Mapped[int] = mapped_column(BigInteger, index=True)
    # FIX: AUDIT-15 - add index for admin CRM queries on user_id
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
