"""Telegram ``user_id`` columns must be 64-bit (BigInteger), never int4.

Telegram user ids have crossed 2^31, so an INTEGER (int4) column overflows on
PostgreSQL (``NumericValueOutOfRange``) for modern users. SQLite's dynamic typing
stores the value regardless, so a runtime insert can't catch the regression on the
test backend — assert the *declared* column type instead. Guards migration
0022_widen_user_id_bigint.
"""
from __future__ import annotations

from sqlalchemy import BigInteger

from core.models import (
    Complaint,
    GalleryItem,
    MessageFeedback,
    SupportMessage,
    Transaction,
    User,
    UserNote,
    UserTag,
)

# Every table that stores a Telegram user id.
_TELEGRAM_USER_ID_COLUMNS = [
    (MessageFeedback, "user_id"),
    (Complaint, "user_id"),
    (UserNote, "user_id"),
    (UserTag, "user_id"),
    (SupportMessage, "user_id"),
    # Anchors — already correct; included so a future narrowing regresses loudly.
    (User, "user_id"),
    (Transaction, "user_id"),
    (GalleryItem, "user_id"),
]


def test_telegram_user_id_columns_are_64bit():
    offenders = [
        f"{model.__tablename__}.{col}"
        for model, col in _TELEGRAM_USER_ID_COLUMNS
        if not isinstance(model.__table__.c[col].type, BigInteger)
    ]
    assert not offenders, f"Telegram id columns must be BigInteger: {offenders}"
