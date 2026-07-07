"""Abandoned-cart checkout intents (ТЗ §7).

Creates ``checkout_intents``: a purchase intent recorded when a user reaches the pay
step (Stars invoice or external checkout), flipped ``completed_at`` on payment. A
scheduler nudges still-open carts older than an admin window (``reminded_at`` keeps the
nudge one-shot). Additive + idempotent; created only if absent (fresh schema uses
create_all).

Revision ID: 0036_checkout_intents
Revises: 0035_user_ad_reply_count
Create Date: 2026-06-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_checkout_intents"
down_revision = "0035_user_ad_reply_count"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "checkout_intents" in _tables():
        return
    op.create_table(
        "checkout_intents",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("resume_cb", sa.String(length=64), nullable=False),
        sa.Column("gateway", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_checkout_intents_user_id", "checkout_intents", ["user_id"])
    op.create_index(
        "ix_checkout_intents_open", "checkout_intents",
        ["completed_at", "reminded_at", "created_at"],
    )


def downgrade() -> None:
    if "checkout_intents" in _tables():
        op.drop_table("checkout_intents")
