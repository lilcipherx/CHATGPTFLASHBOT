"""users.bot_id index (Loop L4, finding F2)

The model declares ``index=True`` on ``users.bot_id`` (FK ``bot_instances.id`` ON
DELETE SET NULL). Migration 0015 added the column and 0037 added the FK, but no
migration ever created the index — so a real Postgres deploy was missing
``ix_users_bot_id``. That index backs the admin multi-bot dashboard filter
(``WHERE bot_id = ?``) and, crucially, keeps ``ON DELETE SET NULL`` from full-scanning
``users`` every time a ``BotInstance`` is deleted. ``scripts.check_migrations`` filters
index-only diffs as SQLite-benign, which is why the gap slipped through.

Mirrors the safe backfill-index pattern already used in 0004/0007/0021/0023: build
CONCURRENTLY on Postgres inside an autocommit block so a plain ``CREATE INDEX`` doesn't
take a SHARE lock blocking all writes on the hot ``users`` table for the whole build;
plain create on SQLite. Idempotent so create_all-built dev DBs are untouched.

Revision ID: 0043_users_bot_id_index
Revises: 0042_search_model
Create Date: 2026-07-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043_users_bot_id_index"
down_revision = "0042_search_model"
branch_labels = None
depends_on = None


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return any(ix["name"] == name for ix in insp.get_indexes(table))


def upgrade() -> None:
    # Idempotent: scripts.init_db (create_all) builds this index from the model on
    # fresh dev DBs, so only create it when missing.
    if "users" not in sa.inspect(op.get_bind()).get_table_names():
        return
    if _has_index("users", "ix_users_bot_id"):
        return
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.create_index(
                "ix_users_bot_id",
                "users",
                ["bot_id"],
                unique=False,
                postgresql_concurrently=True,
            )
    else:
        op.create_index("ix_users_bot_id", "users", ["bot_id"], unique=False)


def downgrade() -> None:
    if not _has_index("users", "ix_users_bot_id"):
        return
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index(
                "ix_users_bot_id", table_name="users", postgresql_concurrently=True
            )
    else:
        op.drop_index("ix_users_bot_id", table_name="users")
