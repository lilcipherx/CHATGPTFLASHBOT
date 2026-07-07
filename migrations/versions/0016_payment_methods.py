"""payment_methods — reusable saved tokens for Premium auto-renewal (ТЗ §6)

Additive + idempotent. Fresh schema is provisioned via create_all, so the table
is created only if absent.

Revision ID: 0016_payment_methods
Revises: 0015_multibot
Create Date: 2026-06-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_payment_methods"
down_revision = "0015_multibot"
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
    if not _has("payment_methods"):
        op.create_table(
            "payment_methods",
            sa.Column("id", _BIGPK, primary_key=True),
            sa.Column("user_id", _BIG, nullable=False),
            sa.Column("gateway", sa.String(20), nullable=False),
            sa.Column("token", sa.String(200), nullable=False),
            sa.Column("customer_id", sa.String(200)),
            sa.Column("brand", sa.String(20)),
            sa.Column("last4", sa.String(4)),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
            *_ts(),
            sa.UniqueConstraint("user_id", "gateway", name="uq_payment_method_user_gw"),
        )
        op.create_index("ix_payment_methods_user_id", "payment_methods", ["user_id"])


def downgrade() -> None:
    if _has("payment_methods"):
        op.drop_table("payment_methods")
