"""rename the in-app currency diamonds -> credits

Renames ``users.diamonds`` -> ``users.credits`` and backfills the stored string
values that named the currency (``transactions.product``,
``generation_jobs.pack_type``, ``promo_codes.reward_type`` = 'diamonds' -> 'credits')
so existing rows keep matching the renamed code paths.

Idempotent: scripts.init_db (create_all) builds fresh dev DBs straight from the
model (already ``credits``), so the column rename only runs when the old column is
still present. The UPDATEs are no-ops once converted, so re-running is safe.

Revision ID: 0005_rename_diamonds_to_credits
Revises: 0004_user_indexes
Create Date: 2026-06-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_rename_diamonds_to_credits"
down_revision = "0004_user_indexes"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    # Column rename (batch mode → works on both SQLite and Postgres). Guarded so a
    # fresh create_all DB (already 'credits') is left untouched.
    if _has_column("users", "diamonds") and not _has_column("users", "credits"):
        with op.batch_alter_table("users") as batch:
            batch.alter_column("diamonds", new_column_name="credits")

    # Backfill the stored currency-name strings in existing rows.
    op.execute("UPDATE transactions SET product = 'credits' WHERE product = 'diamonds'")
    op.execute("UPDATE generation_jobs SET pack_type = 'credits' WHERE pack_type = 'diamonds'")
    op.execute("UPDATE promo_codes SET reward_type = 'credits' WHERE reward_type = 'diamonds'")


def downgrade() -> None:
    if _has_column("users", "credits") and not _has_column("users", "diamonds"):
        with op.batch_alter_table("users") as batch:
            batch.alter_column("credits", new_column_name="diamonds")

    op.execute("UPDATE transactions SET product = 'diamonds' WHERE product = 'credits'")
    op.execute("UPDATE generation_jobs SET pack_type = 'diamonds' WHERE pack_type = 'credits'")
    op.execute("UPDATE promo_codes SET reward_type = 'diamonds' WHERE reward_type = 'credits'")
