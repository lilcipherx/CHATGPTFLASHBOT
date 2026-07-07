"""Public gallery with moderation (ТЗ §4).

A user submits one of their generated images to a public gallery; a moderator
approves or rejects it; approved items are shown in a public Mini App gallery."""
from __future__ import annotations

from sqlalchemy import BigInteger, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin
from core.models.types import BigIntPK


class GalleryItem(Base, TimestampMixin):
    __tablename__ = "gallery_items"
    # The public list + the moderation queue both filter by status, so index it.
    __table_args__ = (Index("ix_gallery_status", "status"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    image_url: Mapped[str] = mapped_column(String(500))
    prompt: Mapped[str | None] = mapped_column(Text)
    # pending | approved | rejected
    status: Mapped[str] = mapped_column(String(20), default="pending")
    moderated_by: Mapped[int | None] = mapped_column(BigInteger)
