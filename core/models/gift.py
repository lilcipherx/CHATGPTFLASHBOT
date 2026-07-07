"""Gift a subscription / pack / credit top-up to another user (ТЗ §6).

The buyer pays for a Gift; a short, shareable ``code`` is generated. A *different*
user redeems the code to receive the entitlement (premium / pack / credits). The
row is the single source of truth for both the payment idempotency (one Gift per
gateway charge) and the redemption idempotency (status flips paid -> redeemed once).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin
from core.models.types import BigIntPK


class Gift(Base, TimestampMixin):
    """One purchased gift, redeemable once by someone other than the buyer."""

    __tablename__ = "gifts"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    # Short shareable token the recipient redeems with /redeem <code>.
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    # FIX: AUDIT-15 - add index for admin support queries
    buyer_id: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(10))      # sub | pack | credits
    product: Mapped[str] = mapped_column(String(40))   # premium | image_pack | ...
    months: Mapped[int | None] = mapped_column(Integer)  # for kind=sub
    qty: Mapped[int | None] = mapped_column(Integer)     # for kind=pack/credits

    gateway: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(Integer, default=0)
    # Unique payment id from the gateway — guards against double-creating a Gift
    # on a webhook / successful_payment retry (mirrors Transaction.gateway_tx_id).
    gateway_tx_id: Mapped[str | None] = mapped_column(String(120), unique=True)

    status: Mapped[str] = mapped_column(String(12), default="paid")  # paid | redeemed
    # FIX: AUDIT-15 - add index
    redeemed_by: Mapped[int | None] = mapped_column(BigInteger, index=True)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
