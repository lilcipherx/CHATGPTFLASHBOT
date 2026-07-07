"""ai_accounts.spend_limit_micros — hard spend cap / лимиты трат (ТЗ §2)

Additive + idempotent. Fresh schema is provisioned via create_all, so the column
is added only if absent.

Revision ID: 0020_account_spend_limit
Revises: 0019_routing_spend
Create Date: 2026-06-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_account_spend_limit"
down_revision = "0019_routing_spend"
branch_labels = None
depends_on = None

_BIG = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if "spend_limit_micros" not in _cols("ai_accounts"):
        op.add_column(
            "ai_accounts",
            sa.Column("spend_limit_micros", _BIG, server_default="0", nullable=False),
        )


def downgrade() -> None:
    if "spend_limit_micros" in _cols("ai_accounts"):
        op.drop_column("ai_accounts", "spend_limit_micros")
