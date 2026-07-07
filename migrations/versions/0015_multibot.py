"""multi-bot / white-label: bot_instances table + users.bot_id (ТЗ §0)

Additive + idempotent. Fresh schema is provisioned via create_all, so each object
is created only if absent.

Revision ID: 0015_multibot
Revises: 0014_user_auto_renew
Create Date: 2026-06-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_multibot"
down_revision = "0014_user_auto_renew"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if "bot_instances" not in _tables():
        op.create_table(
            "bot_instances",
            # BIGSERIAL on Postgres; degrade to INTEGER on SQLite so the PK is the
            # rowid alias and auto-increments (a BIGINT PK does NOT auto-assign on
            # SQLite — inserts would fail the NOT NULL id constraint). Mirrors the
            # model's BigIntPK (core/models/types.py).
            sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
                      primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(length=80), nullable=False),
            sa.Column("token", sa.Text(), nullable=False),
            sa.Column("tg_bot_id", sa.BigInteger(), nullable=True, unique=True),
            sa.Column("username", sa.String(length=64), nullable=True),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "bot_id" not in _cols("users"):
        op.add_column("users", sa.Column("bot_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    if "bot_id" in _cols("users"):
        op.drop_column("users", "bot_id")
    if "bot_instances" in _tables():
        op.drop_table("bot_instances")
