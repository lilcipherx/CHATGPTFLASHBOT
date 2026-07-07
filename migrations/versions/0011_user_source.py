"""users.source — first-touch traffic attribution (ТЗ §7)

Additive + idempotent. Fresh schema is provisioned via create_all, so the column
is added only if absent.

Revision ID: 0011_user_source
Revises: 0010_support_gallery
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_user_source"
down_revision = "0010_support_gallery"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if "source" not in _cols("users"):
        op.add_column("users", sa.Column("source", sa.String(length=64), nullable=True))


def downgrade() -> None:
    if "source" in _cols("users"):
        op.drop_column("users", "source")
