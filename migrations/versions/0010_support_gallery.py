"""support_messages + gallery_items (ТЗ §7 support inbox, §4 public gallery)

Batched table-creation for the wave-2 parallel features. Additive + idempotent —
fresh schema is provisioned via create_all, so each table is created only if absent.

Revision ID: 0010_support_gallery
Revises: 0009_gifts_feedback_crm
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_support_gallery"
down_revision = "0009_gifts_feedback_crm"
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
    if not _has("support_messages"):
        op.create_table(
            "support_messages",
            sa.Column("id", _BIGPK, primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("direction", sa.String(3), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("admin_id", sa.Integer()),
            sa.Column("handled", sa.Boolean(), server_default=sa.false(), nullable=False),
            *_ts(),
        )
        op.create_index("ix_support_messages_user_id", "support_messages", ["user_id"])

    if not _has("gallery_items"):
        op.create_table(
            "gallery_items",
            sa.Column("id", _BIGPK, primary_key=True),
            sa.Column("user_id", _BIG, nullable=False),
            sa.Column("image_url", sa.String(500), nullable=False),
            sa.Column("prompt", sa.Text()),
            sa.Column("status", sa.String(20), server_default="pending", nullable=False),
            sa.Column("moderated_by", _BIG),
            *_ts(),
        )
        op.create_index("ix_gallery_items_user_id", "gallery_items", ["user_id"])
        op.create_index("ix_gallery_status", "gallery_items", ["status"])


def downgrade() -> None:
    for table in ("gallery_items", "support_messages"):
        if _has(table):
            op.drop_table(table)
