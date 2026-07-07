"""Payments, generation jobs, pricing overrides, promo codes."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin
from core.models.types import BigIntPK, JSONType, UUIDType


class Transaction(Base):
    __tablename__ = "transactions"
    # The §8 revenue/DAU dashboards filter (status='paid', created_at >= window)
    # on every load. This composite turns that into an index range read at scale and
    # — since its leading column is ``status`` — also serves every status-only lookup,
    # so a separate standalone ``status`` index would be redundant (omitted).
    __table_args__ = (
        Index("ix_transactions_status_created", "status", "created_at"),
    )

    tx_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    product: Mapped[str] = mapped_column(String(30))
    duration_months: Mapped[int | None] = mapped_column(Integer)
    qty: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(10), default="stars")
    gateway: Mapped[str] = mapped_column(String(20), index=True)
    gateway_tx_id: Mapped[str | None] = mapped_column(String(120), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    credits_added: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    # Composite indexes for the two hot access patterns at scale:
    #  * (user_id, service, created_at) — the Mini App history/refund queries that
    #    filter by user + service and order by created_at;
    #  * (status, created_at) — the stuck-job sweep that scans pending/processing
    #    jobs oldest-first.
    __table_args__ = (
        Index("ix_genjobs_user_service_created", "user_id", "service", "created_at"),
        Index("ix_genjobs_status_created", "status", "created_at"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    service: Mapped[str] = mapped_column(String(50))
    model_variant: Mapped[str | None] = mapped_column(String(50))
    params: Mapped[dict] = mapped_column(JSONType, default=dict)
    cost_credits: Mapped[int] = mapped_column(Integer, default=0)
    pack_type: Mapped[str | None] = mapped_column(String(10))  # image|video|music
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    result_file_id: Mapped[str | None] = mapped_column(String(200))
    result_url: Mapped[str | None] = mapped_column(String(500))
    provider_job_id: Mapped[str | None] = mapped_column(String(120))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Stamped the first (and only) time refund_job reverses this job's charge.
    # refund_job claims it with a conditional UPDATE (refunded_at IS NULL), so the
    # charge is returned at most once no matter how many callers/retries reach it —
    # idempotency lives on the row, not in each caller's hand-rolled status re-check.
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Pricing(Base):
    """Runtime-editable business numbers (prices, multipliers, rewards)."""

    __tablename__ = "pricing"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType)


class PromoCode(Base):
    __tablename__ = "promo_codes"

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    # credits | image | video | music (pack) | premium (reward_amount = days)
    reward_type: Mapped[str] = mapped_column(String(20))
    reward_amount: Mapped[int] = mapped_column(Integer)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Audience gate: when > 0, only accounts younger than this many days may redeem
    # (anti-abuse / new-user-only campaigns). 0 = open to all users.
    new_user_days: Mapped[int] = mapped_column(Integer, default=0)


class CheckoutIntent(Base):
    """A recorded purchase intent (ТЗ §7 abandoned-cart): written when a user reaches
    the pay step (Stars invoice or external checkout) and flipped ``completed_at`` on a
    successful payment. A scheduler nudges still-open carts older than an admin window
    (``reminded_at`` makes the nudge one-shot per cart). ``resume_cb`` is the bot
    callback that re-opens the same product's menu."""

    __tablename__ = "checkout_intents"
    __table_args__ = (
        Index("ix_checkout_intents_open", "completed_at", "reminded_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(20))         # sub | pack | credits | avatar
    resume_cb: Mapped[str] = mapped_column(String(64))    # callback that re-opens the menu
    gateway: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(Integer, default=0)  # Stars price (display)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentMethod(Base, TimestampMixin):
    """A reusable payment token saved at checkout so Premium auto-renewal can charge
    recurringly without user interaction (ТЗ §6).

    One active row per (user, gateway) — re-saving updates it in place. ``token`` is
    the gateway's saved-method id (YooKassa ``payment_method_id`` / Stripe
    ``payment_method``); ``customer_id`` is the Stripe customer the method is attached
    to (None for YooKassa). ``brand``/``last4`` are display-only. ``is_active`` is
    flipped off if a recurring charge is later declined for a dead method."""

    __tablename__ = "payment_methods"
    __table_args__ = (
        UniqueConstraint("user_id", "gateway", name="uq_payment_method_user_gw"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    gateway: Mapped[str] = mapped_column(String(20))  # yookassa | stripe
    token: Mapped[str] = mapped_column(String(200))
    customer_id: Mapped[str | None] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(20))
    last4: Mapped[str | None] = mapped_column(String(4))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Broadcast(Base, TimestampMixin):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    segment: Mapped[dict] = mapped_column(JSONType, default=dict)
    content: Mapped[dict] = mapped_column(JSONType, default=dict)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    sent: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
