"""User + per-user config + pack balances."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.constants import DEFAULT_MODEL, DEFAULT_VOICE
from core.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"
    # Partial index for the admin dashboard's banned-user count: on Postgres it
    # covers only the (tiny) banned subset; the WHERE is ignored on SQLite, which
    # just builds a plain index there.
    __table_args__ = (
        Index("ix_users_is_banned", "is_banned", postgresql_where=text("is_banned")),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    language_code: Mapped[str] = mapped_column(String(5), default="ru")
    # captured when the user shares their contact in the bot (optional); country
    # is derived from the phone's country code (see core.services.notifications).
    phone: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(2))  # ISO-3166 alpha-2

    # per-user config (§9 settings)
    selected_model: Mapped[str] = mapped_column(String(50), default=DEFAULT_MODEL)
    custom_role: Mapped[str | None] = mapped_column(Text)
    role_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    context_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    voice_name: Mapped[str] = mapped_column(String(20), default=DEFAULT_VOICE)
    voice_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # An applied discount promo code (reward_type="discount"): set by /promo, charged
    # at max(sale%, code%) on the next purchase, then cleared + the slot spent on a
    # successful payment (ТЗ §4). None = no code applied.
    discount_code: Mapped[str | None] = mapped_column(String(40))

    # subscription
    sub_tier: Mapped[str | None] = mapped_column(String(20))  # premium | premium_x2
    # indexed: hourly expiry-sweep cron filters on this column
    sub_expires: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    # The user's explicit consent to auto-renew Premium (ТЗ §6). Opt-in: default
    # False. When True and the subscription is nearing expiry, the daily
    # auto-renewal cron (see core.services.autorenew) attempts a recurring charge.
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)

    # dual quota counters (§10.1)
    text_req_week: Mapped[int] = mapped_column(Integer, default=0)
    week_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    text_req_day: Mapped[int] = mapped_column(Integer, default=0)
    day_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mini_app_effects_week: Mapped[int] = mapped_column(Integer, default=0)
    mini_app_week_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Lifetime monotonic counter of free-user replies, used ONLY to pace ad injection
    # (ТЗ §6): it ticks on every reply regardless of pay source, so the "ad every Nth
    # reply" cadence never freezes once a free user is paying from their ✨ balance
    # (the quota counters stop advancing past the limit). Never reset.
    ad_reply_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Per-UTC-day counter of FREE sponsored-effect generations the user has used
    # (sponsor pays up to the admin cap; reset when the date rolls over).
    sponsored_free_day: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sponsored_free_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    credits: Mapped[int] = mapped_column(Integer, default=0)
    # Daily login-streak bonus (§ daily bonus): last claim time + current streak.
    last_bonus_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bonus_streak: Mapped[int] = mapped_column(Integer, default=0)
    is_channel_subscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    referred_by: Mapped[int | None] = mapped_column(BigInteger)
    # Traffic-source attribution (ТЗ §7): first-touch deep-link token captured from
    # /start. Set ONCE at signup and never overwritten. NULL = direct / unknown.
    source: Mapped[str | None] = mapped_column(String(64))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    # Multi-bot / white-label tenant (ТЗ §0): which BotInstance this user arrived
    # through. NULL = the primary/legacy bot (single-bot deployments). Set once at
    # signup. The same Telegram user_id on two bots stays ONE row keyed by user_id
    # here (soft tenancy for attribution/segmentation); hard per-bot isolation
    # (composite keys) is a later increment.
    bot_id: Mapped[int | None] = mapped_column(
        BigInteger,
        # FIX: F31 - FK + index for referential integrity (deleting a BotInstance
        # SET NULLs users.bot_id instead of orphaning) and perf on admin multi-bot
        # dashboards (WHERE bot_id = ?). Migration 0037 adds the FK on existing DBs.
        ForeignKey("bot_instances.id", ondelete="SET NULL"),
        index=True,
    )

    balances: Mapped[PackBalance] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def is_premium(self) -> bool:
        from datetime import datetime

        if not (self.sub_tier and self.sub_expires):
            return False
        expires = self.sub_expires
        if expires.tzinfo is None:  # SQLite returns naive datetimes
            expires = expires.replace(tzinfo=UTC)
        return expires > datetime.now(UTC)


class PackBalance(Base):
    __tablename__ = "pack_balances"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    image_credits: Mapped[int] = mapped_column(Integer, default=0)
    video_credits: Mapped[int] = mapped_column(Integer, default=0)
    music_credits: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship(back_populates="balances")
