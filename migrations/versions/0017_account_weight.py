"""ai_accounts.weight — weighted load-balancing across same-tier accounts (ТЗ §2)

Additive + idempotent. Fresh schema is provisioned via create_all, so the column
is added only if absent.

Revision ID: 0017_account_weight
Revises: 0016_payment_methods
Create Date: 2026-06-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_account_weight"
down_revision = "0016_payment_methods"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if "weight" not in _cols("ai_accounts"):
        op.add_column(
            "ai_accounts",
            sa.Column("weight", sa.Integer(), server_default="1", nullable=False),
        )


def downgrade() -> None:
    if "weight" in _cols("ai_accounts"):
        op.drop_column("ai_accounts", "weight")
