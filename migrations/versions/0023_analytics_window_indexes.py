"""analytics window indexes — transactions(status,created_at) + usage_log(created_at)

The §8 revenue/DAU dashboards scan transactions by (status='paid', created_at >=
window) and usage_log by (created_at >= window) on every load. transactions had only
a standalone status index (no created_at bound) and usage_log only a user_id index,
so both queries degraded to full scans at scale — the same gap generation_jobs already
closed with its (status, created_at) composite.

Add transactions(status, created_at) and usage_log(created_at). Drop the now-redundant
standalone transactions(status) index — the composite's leading column already serves
every status-only lookup. Additive + idempotent: each change is guarded so a fresh
create_all DB (already carrying the composite) and re-runs are no-ops.

Revision ID: 0023_analytics_window_indexes
Revises: 0022_widen_user_id_bigint
Create Date: 2026-06-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_analytics_window_indexes"
down_revision = "0022_widen_user_id_bigint"
branch_labels = None
depends_on = None


def _indexes(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    tx = _indexes("transactions")
    if "transactions" in sa.inspect(op.get_bind()).get_table_names():
        if "ix_transactions_status_created" not in tx:
            # FIX: C6 - CONCURRENTLY needs autocommit_block on Postgres.
            with op.get_context().autocommit_block():
                op.create_index(
                    "ix_transactions_status_created",
                    "transactions",
                    ["status", "created_at"],
                    postgresql_concurrently=True,
                )
        # Redundant once the composite (leading col = status) exists.
        if "ix_transactions_status" in tx:
            op.drop_index("ix_transactions_status", table_name="transactions")

    if "ix_usage_log_created_at" not in _indexes("usage_log"):
        if "usage_log" in sa.inspect(op.get_bind()).get_table_names():
            # FIX: C6 - CONCURRENTLY needs autocommit_block on Postgres.
            with op.get_context().autocommit_block():
                op.create_index(
                    "ix_usage_log_created_at", "usage_log", ["created_at"],
                    postgresql_concurrently=True,
                )


def downgrade() -> None:
    ul = _indexes("usage_log")
    if "ix_usage_log_created_at" in ul:
        op.drop_index("ix_usage_log_created_at", table_name="usage_log")

    tx = _indexes("transactions")
    if "transactions" in sa.inspect(op.get_bind()).get_table_names():
        if "ix_transactions_status" not in tx:
            op.create_index("ix_transactions_status", "transactions", ["status"])
        if "ix_transactions_status_created" in tx:
            op.drop_index(
                "ix_transactions_status_created", table_name="transactions"
            )
