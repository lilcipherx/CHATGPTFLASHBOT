"""Drop the agent/affiliate program (ТЗ §6 — removed).

The agent program (a manually-designated partner tier with a %-commission on their
referees' purchases, paid out off-platform) is being removed: the consumer referral
loop (``referrals``) covers organic growth, and the agent tier was never used. This
drops its two tables. The downgrade recreates them empty (the historical
0013_agent_program migration defined their original shape) so the chain stays
reversible, but the service/model/admin code is gone.

Revision ID: 0032_drop_agent_program
Revises: 0031_contest_prize
Create Date: 2026-06-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_drop_agent_program"
down_revision = "0031_contest_prize"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "agent_earnings" in tables:
        op.drop_table("agent_earnings")
    if "agents" in tables:
        op.drop_table("agents")


def downgrade() -> None:
    tables = _tables()
    if "agents" not in tables:
        op.create_table(
            "agents",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("commission_pct", sa.Integer(), nullable=False, server_default="10"),
            sa.Column("credits_per_referral", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", name="uq_agent_user"),
        )
    if "agent_earnings" not in tables:
        op.create_table(
            "agent_earnings",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("agent_id", sa.BigInteger(), nullable=False, index=True),
            sa.Column("buyer_id", sa.BigInteger(), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=8), nullable=False),
            sa.Column("commission", sa.Integer(), nullable=False),
            sa.Column("credits_awarded", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("ref", sa.String(length=120), unique=True),
            sa.Column("paid_out", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
