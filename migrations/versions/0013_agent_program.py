"""agents + agent_earnings — agent/affiliate program (ТЗ §6)

Additive + idempotent. Fresh schema is provisioned via create_all, so each table
is created only if absent.

Revision ID: 0013_agent_program
Revises: 0012_contests_channel
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_agent_program"
down_revision = "0012_contests_channel"
branch_labels = None
depends_on = None

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
    if not _has("agents"):
        op.create_table(
            "agents",
            sa.Column("id", _BIGPK, primary_key=True),
            sa.Column("user_id", _BIG, nullable=False),
            sa.Column("commission_pct", sa.Integer(), server_default="10", nullable=False),
            sa.Column("credits_per_referral", sa.Integer(), server_default="0", nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            *_ts(),
            sa.UniqueConstraint("user_id", name="uq_agent_user"),
        )

    if not _has("agent_earnings"):
        op.create_table(
            "agent_earnings",
            sa.Column("id", _BIGPK, primary_key=True),
            sa.Column("agent_id", _BIG, nullable=False),
            sa.Column("buyer_id", _BIG, nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(8), nullable=False),
            sa.Column("commission", sa.Integer(), nullable=False),
            sa.Column("credits_awarded", sa.Integer(), server_default="0", nullable=False),
            sa.Column("ref", sa.String(120)),
            sa.Column("paid_out", sa.Boolean(), server_default=sa.false(), nullable=False),
            *_ts(),
            sa.UniqueConstraint("ref", name="uq_agent_earning_ref"),
        )
        op.create_index("ix_agent_earnings_agent_id", "agent_earnings", ["agent_id"])


def downgrade() -> None:
    for table in ("agent_earnings", "agents"):
        if _has(table):
            op.drop_table(table)
