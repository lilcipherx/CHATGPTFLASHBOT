"""users.auto_renew — Premium auto-renewal opt-in (ТЗ §6)

Additive + idempotent. Fresh schema is provisioned via create_all, so the column
is added only if absent.

Revision ID: 0014_user_auto_renew
Revises: 0013_agent_program
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_user_auto_renew"
down_revision = "0013_agent_program"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if "auto_renew" not in _cols("users"):
        op.add_column(
            "users",
            sa.Column("auto_renew", sa.Boolean(), server_default=sa.false(), nullable=False),
        )


def downgrade() -> None:
    if "auto_renew" in _cols("users"):
        op.drop_column("users", "auto_renew")
