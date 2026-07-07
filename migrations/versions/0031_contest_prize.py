"""Contest auto-prize — admin-set reward granted to winners on draw (ТЗ §7).

A contest can now carry a prize the bot grants automatically when winners are
drawn, instead of the admin topping up each winner by hand:
  * ``contests.prize_type`` — "credits" | "image" | "video" | "music" (mirrors the
    promo reward vocabulary). Defaults to "credits".
  * ``contests.prize_amount`` — how much (✨ for credits, pack units otherwise).
    ``0`` (the default) means "no auto-prize" — behaviour is unchanged: winners are
    only notified and the admin grants manually.

Additive + idempotent; existing rows default to credits/0 (i.e. notify-only, as
before). Fresh schema is provisioned via create_all, so columns are added only if
absent.

Revision ID: 0031_contest_prize
Revises: 0030_sponsored_effects
Create Date: 2026-06-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_contest_prize"
down_revision = "0030_sponsored_effects"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = _cols("contests")
    if not cols:
        return
    if "prize_type" not in cols:
        op.add_column("contests", sa.Column(
            "prize_type", sa.String(length=12), nullable=False, server_default="credits"))
    if "prize_amount" not in cols:
        op.add_column("contests", sa.Column(
            "prize_amount", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    cols = _cols("contests")
    if "prize_amount" in cols:
        op.drop_column("contests", "prize_amount")
    if "prize_type" in cols:
        op.drop_column("contests", "prize_type")
