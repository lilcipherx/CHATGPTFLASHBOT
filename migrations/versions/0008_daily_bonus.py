"""daily login-streak bonus: users.last_bonus_at + users.bonus_streak

Additive, idempotent (this project provisions fresh schema via create_all, so only
add what's missing).

(Renumbered from 0007_daily_bonus to 0008 to resolve a dual-0007 head: the parallel
session's daily-bonus migration and the search/job-index migration both branched off
0006. Now linear: 0006 -> 0007_search_job_indexes -> 0008_daily_bonus.)

Revision ID: 0008_daily_bonus
Revises: 0007_search_job_indexes
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_daily_bonus"
down_revision = "0007_search_job_indexes"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    have = _cols("users")
    if "last_bonus_at" not in have:
        op.add_column("users", sa.Column("last_bonus_at", sa.DateTime(timezone=True), nullable=True))
    if "bonus_streak" not in have:
        op.add_column("users", sa.Column("bonus_streak", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    have = _cols("users")
    if "bonus_streak" in have:
        op.drop_column("users", "bonus_streak")
    if "last_bonus_at" in have:
        op.drop_column("users", "last_bonus_at")
