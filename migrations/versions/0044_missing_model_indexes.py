"""backfill model-declared indexes never migrated (Loop L4, finding F3)

Same class as F2 (0043): these columns declare ``index=True`` on the model but no
migration ever created the index, so a real Postgres deploy was missing them —
``create_all`` dev DBs and the SQLite test fixtures build them from the model, and
``scripts.check_migrations`` filters index-only diffs as SQLite-benign, so the gap was
invisible. Backfilled here:

- ``gifts.buyer_id``    — list a buyer's sent gifts / gifting history.
- ``gifts.redeemed_by`` — find gifts redeemed by a user.
- ``contest_entries.user_id`` — admin CRM queries per user (the model comment
  "AUDIT-15 - add index for admin CRM queries on user_id" added it to the model only).

(``contest_entries.contest_id`` is already covered by the leading column of the
``uq_contest_entry (contest_id, user_id)`` unique index; ``gifts.code`` by its UNIQUE.)

Mirrors the 0004/0043 safe backfill pattern: CONCURRENTLY on Postgres inside an
autocommit block, plain create on SQLite; idempotent + reversible.

Revision ID: 0044_missing_model_indexes
Revises: 0043_users_bot_id_index
Create Date: 2026-07-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_missing_model_indexes"
down_revision = "0043_users_bot_id_index"
branch_labels = None
depends_on = None

# (index name, table, column)
_INDEXES = [
    ("ix_gifts_buyer_id", "gifts", "buyer_id"),
    ("ix_gifts_redeemed_by", "gifts", "redeemed_by"),
    ("ix_contest_entries_user_id", "contest_entries", "user_id"),
]


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return any(ix["name"] == name for ix in insp.get_indexes(table))


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    is_pg = op.get_bind().dialect.name == "postgresql"
    for name, table, column in _INDEXES:
        if table not in tables or _has_index(table, name):
            continue
        if is_pg:
            with op.get_context().autocommit_block():
                op.create_index(
                    name, table, [column], unique=False, postgresql_concurrently=True
                )
        else:
            op.create_index(name, table, [column], unique=False)


def downgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"
    for name, table, _ in reversed(_INDEXES):
        if not _has_index(table, name):
            continue
        if is_pg:
            with op.get_context().autocommit_block():
                op.drop_index(name, table_name=table, postgresql_concurrently=True)
        else:
            op.drop_index(name, table_name=table)
