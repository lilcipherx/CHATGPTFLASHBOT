"""gifts + message_feedback + complaints + user_notes + user_tags (ТЗ §6/§7/§9)

Batched table-creation for the parallel wave-4/5 features (gifts to a friend,
👍/👎 ratings + complaints, CRM notes/tags). Additive + idempotent — this project
provisions fresh schema via create_all, so each table is created only if absent.

Revision ID: 0009_gifts_feedback_crm
Revises: 0008_daily_bonus
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_gifts_feedback_crm"
down_revision = "0008_daily_bonus"
branch_labels = None
depends_on = None

# SQLite-safe big-int PK (mirrors core.models.types.BigIntPK).
_BIGPK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
_BIG = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _has(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def _ts() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    ]


def upgrade() -> None:
    if not _has("gifts"):
        op.create_table(
            "gifts",
            sa.Column("id", _BIGPK, primary_key=True),
            sa.Column("code", sa.String(16), nullable=False),
            sa.Column("buyer_id", _BIG, nullable=False),
            sa.Column("kind", sa.String(10), nullable=False),
            sa.Column("product", sa.String(40), nullable=False),
            sa.Column("months", sa.Integer()),
            sa.Column("qty", sa.Integer()),
            sa.Column("gateway", sa.String(20), nullable=False),
            sa.Column("amount", sa.Integer(), server_default="0", nullable=False),
            sa.Column("gateway_tx_id", sa.String(120)),
            sa.Column("status", sa.String(12), server_default="paid", nullable=False),
            sa.Column("redeemed_by", _BIG),
            sa.Column("redeemed_at", sa.DateTime(timezone=True)),
            *_ts(),
            sa.UniqueConstraint("code", name="uq_gifts_code"),
            sa.UniqueConstraint("gateway_tx_id", name="uq_gifts_gateway_tx_id"),
        )
        op.create_index("ix_gifts_code", "gifts", ["code"])

    if not _has("message_feedback"):
        op.create_table(
            "message_feedback",
            sa.Column("id", _BIGPK, primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("rating", sa.String(4), nullable=False),
            sa.Column("snippet", sa.String(200)),
            *_ts(),
        )
        op.create_index("ix_message_feedback_user_id", "message_feedback", ["user_id"])

    if not _has("complaints"):
        op.create_table(
            "complaints",
            sa.Column("id", _BIGPK, primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("resolved", sa.Boolean(), server_default=sa.false(), nullable=False),
            *_ts(),
        )
        op.create_index("ix_complaints_user_id", "complaints", ["user_id"])

    if not _has("user_notes"):
        op.create_table(
            "user_notes",
            sa.Column("id", _BIGPK, primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("admin_id", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_user_notes_user_id", "user_notes", ["user_id"])

    if not _has("user_tags"):
        op.create_table(
            "user_tags",
            sa.Column("id", _BIGPK, primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("tag", sa.String(40), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "tag", name="uq_user_tag"),
        )
        op.create_index("ix_user_tags_user_id", "user_tags", ["user_id"])


def downgrade() -> None:
    for table in ("user_tags", "user_notes", "complaints", "message_feedback", "gifts"):
        if _has(table):
            op.drop_table(table)
