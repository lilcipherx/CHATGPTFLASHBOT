"""contests + contest_entries + channel_posts (ТЗ §7 giveaways + autoposting)

Batched table-creation for the wave-4 parallel features. Additive + idempotent.

Revision ID: 0012_contests_channel
Revises: 0011_user_source
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_contests_channel"
down_revision = "0011_user_source"
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
    if not _has("contests"):
        op.create_table(
            "contests",
            sa.Column("id", _BIGPK, primary_key=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("status", sa.String(12), server_default="open", nullable=False),
            sa.Column("winners_count", sa.Integer(), server_default="1", nullable=False),
            sa.Column("drawn_at", sa.DateTime(timezone=True)),
            *_ts(),
        )

    if not _has("contest_entries"):
        op.create_table(
            "contest_entries",
            sa.Column("id", _BIGPK, primary_key=True),
            sa.Column("contest_id", _BIG, nullable=False),
            sa.Column("user_id", _BIG, nullable=False),
            *_ts(),
            sa.UniqueConstraint("contest_id", "user_id", name="uq_contest_entry"),
        )
        op.create_index("ix_contest_entries_contest_id", "contest_entries", ["contest_id"])

    if not _has("channel_posts"):
        op.create_table(
            "channel_posts",
            sa.Column("id", _BIGPK, primary_key=True),
            sa.Column("channel", sa.String(120), nullable=False),
            sa.Column("text", sa.Text(), nullable=False, server_default=""),
            sa.Column("photo_url", sa.String(500)),
            sa.Column("button_text", sa.String(120)),
            sa.Column("button_url", sa.String(500)),
            sa.Column("scheduled_at", sa.DateTime(timezone=True)),
            sa.Column("status", sa.String(20), server_default="pending", nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True)),
            sa.Column("error", sa.Text()),
            *_ts(),
        )
        op.create_index("ix_channel_posts_status", "channel_posts", ["status"])


def downgrade() -> None:
    for table in ("channel_posts", "contest_entries", "contests"):
        if _has(table):
            op.drop_table(table)
