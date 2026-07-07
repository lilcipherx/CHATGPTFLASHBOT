"""user indexes: partial index on users.is_banned (dashboard banned-count)

Speeds up the admin dashboard's ``COUNT(*) WHERE is_banned`` on large user tables.
On Postgres it is a PARTIAL index covering only banned rows (tiny); on SQLite the
WHERE is ignored and it is a plain index. NULL/false rows are excluded on PG so
the index stays small even at millions of users.

(No index on ``referred_by``: it is only ever read off an already-loaded User row,
never used as a query predicate, so an index there would add write cost for no
read benefit.)

Revision ID: 0004_user_indexes
Revises: 0003_routing_multimodal
Create Date: 2026-06-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_user_indexes"
down_revision = "0003_routing_multimodal"
branch_labels = None
depends_on = None


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return any(ix["name"] == name for ix in insp.get_indexes(table))


def upgrade() -> None:
    # Idempotent: scripts.init_db (create_all) builds this index from the model on
    # fresh dev DBs, so only create it when missing.
    if _has_index("users", "ix_users_is_banned"):
        return
    # FIX: AUDIT13-M24 - build CONCURRENTLY on Postgres inside an autocommit block so a
    # plain CREATE INDEX doesn't take a SHARE lock that blocks all writes on the hot
    # `users` table for the whole build (this is a backfill index on existing DBs).
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.create_index(
                "ix_users_is_banned",
                "users",
                ["is_banned"],
                unique=False,
                postgresql_where=sa.text("is_banned"),
                postgresql_concurrently=True,
            )
    else:
        op.create_index(
            "ix_users_is_banned",
            "users",
            ["is_banned"],
            unique=False,
            postgresql_where=sa.text("is_banned"),
        )


def downgrade() -> None:
    if not _has_index("users", "ix_users_is_banned"):
        return
    # FIX: AUDIT13-M24 - drop CONCURRENTLY on Postgres too (symmetry with the build).
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.drop_index("ix_users_is_banned", table_name="users", postgresql_concurrently=True)
    else:
        op.drop_index("ix_users_is_banned", table_name="users")
