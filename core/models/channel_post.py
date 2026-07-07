"""Channel autoposting (ТЗ §7) — admin schedules a post; a worker publishes it.

Mirrors the scheduled-broadcast shape (scheduled_at + status) but targets a
single Telegram channel instead of a user segment."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin
from core.models.types import BigIntPK


class ChannelPost(Base, TimestampMixin):
    __tablename__ = "channel_posts"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    # "@mychannel" or a numeric chat id stored as a string.
    channel: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text, default="")
    photo_url: Mapped[str | None] = mapped_column(String(500))
    button_text: Mapped[str | None] = mapped_column(String(120))
    button_url: Mapped[str | None] = mapped_column(String(500))
    # None = send as soon as the next cron tick runs.
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
