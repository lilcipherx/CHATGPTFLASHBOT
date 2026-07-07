"""admin_audit_log.created_at index — time-window audit queries (ТЗ §8)

The Audit Center stats (today / last_hour / by_day counts) and any
created_at-bounded audit filters scan the table by timestamp. With the audit
trail growing into the millions of rows, an index on created_at turns those
range scans into index range reads. Additive + idempotent: fresh schema is
provisioned via create_all (the model now declares index=True), so this only
backfills the index on databases created before this revision.

Revision ID: 0021_audit_created_at_index
Revises: 0020_account_spend_limit
Create Date: 2026-06-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_audit_created_at_index"
down_revision = "0020_account_spend_limit"
branch_labels = None
depends_on = None

_INDEX = "ix_admin_audit_log_created_at"
_TABLE = "admin_audit_log"


def _indexes(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {ix["name"] for ix in insp.get_indexes(table)}


def upgrade() -> None:
    if _INDEX not in _indexes(_TABLE):
        # FIX: C5 - CONCURRENTLY needs autocommit_block on Postgres.
        with op.get_context().autocommit_block():
            op.create_index(
                _INDEX, _TABLE, ["created_at"], unique=False,
                postgresql_concurrently=True,
            )


def downgrade() -> None:
    if _INDEX in _indexes(_TABLE):
        op.drop_index(_INDEX, table_name=_TABLE)
