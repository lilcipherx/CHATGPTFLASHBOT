"""routing spend accounting — ai_accounts.spend_micros + ai_models.cost_micros (ТЗ §2)

Additive + idempotent. Fresh schema is provisioned via create_all, so each column
is added only if absent.

Revision ID: 0019_routing_spend
Revises: 0018_account_latency
Create Date: 2026-06-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_routing_spend"
down_revision = "0018_account_latency"
branch_labels = None
depends_on = None

_BIG = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if "spend_micros" not in _cols("ai_accounts"):
        op.add_column(
            "ai_accounts",
            sa.Column("spend_micros", _BIG, server_default="0", nullable=False),
        )
    if "cost_micros" not in _cols("ai_models"):
        op.add_column(
            "ai_models",
            sa.Column("cost_micros", sa.Integer(), server_default="0", nullable=False),
        )


def downgrade() -> None:
    if "spend_micros" in _cols("ai_accounts"):
        op.drop_column("ai_accounts", "spend_micros")
    if "cost_micros" in _cols("ai_models"):
        op.drop_column("ai_models", "cost_micros")
