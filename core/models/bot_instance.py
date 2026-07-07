"""Multi-bot / white-label registry (ТЗ §0).

Each ``BotInstance`` is one Telegram bot token the platform runs on the SAME shared
backend. The launcher (bot.multi) polls every active instance through one
dispatcher, so all bots share handlers/logic while users are attributed to the bot
they came through (``User.bot_id``). The token is stored ENCRYPTED at rest (same
crypto as AI-account keys); ``tg_bot_id``/``username`` are filled on first connect.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin
from core.models.types import BigIntPK


class BotInstance(Base, TimestampMixin):
    """One white-label bot token run on the shared backend."""

    __tablename__ = "bot_instances"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(80))            # admin-facing label
    token: Mapped[str] = mapped_column(Text)                  # encrypted bot token
    # Telegram bot id + @username, discovered via get_me() on first launch.
    tg_bot_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # The default bot owns legacy/NULL-bot_id users + is the fallback for routing.
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
