"""Dedicated ad-pacing counter on a user (ТЗ §6).

Adds ``users.ad_reply_count``: a lifetime monotonic counter of free-user replies
used solely to pace ad injection ("an ad every Nth reply"). It ticks on every reply
regardless of pay source, so the cadence no longer freezes once a free user is
paying from their ✨ balance (the quota counters stop advancing past the limit).

Additive + idempotent; fresh schema is provisioned via create_all, so the column
is added only if absent. server_default '0' backfills existing rows.

Revision ID: 0035_user_ad_reply_count
Revises: 0034_user_discount_code
Create Date: 2026-06-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035_user_ad_reply_count"
down_revision = "0034_user_discount_code"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = _cols("users")
    if cols and "ad_reply_count" not in cols:
        op.add_column("users", sa.Column(
            "ad_reply_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    if "ad_reply_count" in _cols("users"):
        op.drop_column("users", "ad_reply_count")
