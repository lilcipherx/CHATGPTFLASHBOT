"""widen Telegram user_id columns int4 -> int8 (overflow fix)

message_feedback / complaints / user_notes / user_tags / support_messages declared
their ``user_id`` as INTEGER (int4) while every other table stores the Telegram user
id as BIGINT. Telegram user ids have crossed 2^31, so on PostgreSQL an INSERT for a
modern user raised ``NumericValueOutOfRange`` — silently breaking 👍/👎 feedback,
``/report`` complaints, CRM notes/tags and the ``/support`` inbox. SQLite's dynamic
typing stores the 64-bit value regardless, which hid the defect in dev/test.

Widen the five columns to BIGINT on PostgreSQL. No-op on SQLite (its INTEGER column
already holds 64-bit values, and a batch rebuild would be pointless churn). Idempotent
— only columns still typed int4 are altered, so re-running is safe.

Revision ID: 0022_widen_user_id_bigint
Revises: 0021_audit_created_at_index
Create Date: 2026-06-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_widen_user_id_bigint"
down_revision = "0021_audit_created_at_index"
branch_labels = None
depends_on = None

_TABLES = (
    "message_feedback",
    "complaints",
    "user_notes",
    "user_tags",
    "support_messages",
)


def _user_id_type(insp, table):
    for c in insp.get_columns(table):
        if c["name"] == "user_id":
            return c["type"]
    return None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite INTEGER already stores 64-bit ids — nothing to widen.
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())
    for table in _TABLES:
        if table not in existing:
            continue
        col = _user_id_type(insp, table)
        # Only widen columns still typed int4 (idempotent on re-run).
        if isinstance(col, sa.Integer) and not isinstance(col, sa.BigInteger):
            op.alter_column(
                table,
                "user_id",
                type_=sa.BigInteger(),
                existing_type=sa.Integer(),
                existing_nullable=False,
            )


def downgrade() -> None:
    # Narrowing back to int4 only succeeds if no stored id exceeds 2^31-1.
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())
    for table in _TABLES:
        if table not in existing:
            continue
        op.alter_column(
            table,
            "user_id",
            type_=sa.Integer(),
            existing_type=sa.BigInteger(),
            existing_nullable=False,
        )
