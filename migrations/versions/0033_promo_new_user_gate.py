"""Promo audience gate — new-users-only flag (ТЗ §6).

Adds ``promo_codes.new_user_days``: when > 0, the code may only be redeemed by
accounts younger than that many days (anti-abuse / new-user campaigns). 0 (the
default) keeps a code open to everyone, so existing codes are unchanged.

The Premium reward type (reward_type='premium', reward_amount = days) needs no
schema change — it reuses the existing reward_type/reward_amount columns.

Additive + idempotent; fresh schema is provisioned via create_all, so the column
is added only if absent.

Revision ID: 0033_promo_new_user_gate
Revises: 0032_drop_agent_program
Create Date: 2026-06-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_promo_new_user_gate"
down_revision = "0032_drop_agent_program"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = _cols("promo_codes")
    if cols and "new_user_days" not in cols:
        op.add_column("promo_codes", sa.Column(
            "new_user_days", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    if "new_user_days" in _cols("promo_codes"):
        op.drop_column("promo_codes", "new_user_days")
