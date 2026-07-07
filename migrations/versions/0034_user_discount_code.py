"""Applied discount promo code on a user (ТЗ §4).

Adds ``users.discount_code``: the discount promo a user has applied via /promo
(reward_type='discount'). On the next purchase the price is charged at
max(sale%, code%), then the column is cleared and the code's use slot spent. NULL
(the default) means no code is applied, so existing users are unchanged.

Additive + idempotent; fresh schema is provisioned via create_all, so the column
is added only if absent.

Revision ID: 0034_user_discount_code
Revises: 0033_promo_new_user_gate
Create Date: 2026-06-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_user_discount_code"
down_revision = "0033_promo_new_user_gate"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = _cols("users")
    if cols and "discount_code" not in cols:
        op.add_column("users", sa.Column("discount_code", sa.String(length=40), nullable=True))


def downgrade() -> None:
    if "discount_code" in _cols("users"):
        op.drop_column("users", "discount_code")
