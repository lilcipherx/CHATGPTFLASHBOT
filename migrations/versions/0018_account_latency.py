"""ai_accounts latency columns — per-account latency/uptime tracking (ТЗ §2)

Additive + idempotent. Fresh schema is provisioned via create_all, so each column
is added only if absent.

Revision ID: 0018_account_latency
Revises: 0017_account_weight
Create Date: 2026-06-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_account_latency"
down_revision = "0017_account_weight"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = _cols("ai_accounts")
    if "ai_accounts" not in sa.inspect(op.get_bind()).get_table_names():
        return
    if "last_latency_ms" not in cols:
        op.add_column("ai_accounts", sa.Column("last_latency_ms", sa.Integer(), nullable=True))
    if "avg_latency_ms" not in cols:
        op.add_column(
            "ai_accounts",
            sa.Column("avg_latency_ms", sa.Integer(), server_default="0", nullable=False),
        )


def downgrade() -> None:
    cols = _cols("ai_accounts")
    if "avg_latency_ms" in cols:
        op.drop_column("ai_accounts", "avg_latency_ms")
    if "last_latency_ms" in cols:
        op.drop_column("ai_accounts", "last_latency_ms")
