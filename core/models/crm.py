"""CRM: free-text notes and tags an admin can attach to a user (ТЗ §9).

Both models self-register with ``Base.metadata`` on import, so tests that call
``Base.metadata.create_all()`` pick them up without a migration.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base
from core.models.types import BigIntPK


class UserNote(Base):
    """A free-text note an admin left on a user's card."""

    __tablename__ = "user_notes"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    # Telegram user id — 64-bit (int4 overflows on Postgres for modern ids).
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    # FIX: AUDIT-15 - BigInteger to match AdminUser.id type
    admin_id: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserTag(Base):
    """A short label attached to a user. Unique per (user_id, tag)."""

    __tablename__ = "user_tags"
    __table_args__ = (UniqueConstraint("user_id", "tag", name="uq_user_tag"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    # Telegram user id — 64-bit (int4 overflows on Postgres for modern ids).
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    tag: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
