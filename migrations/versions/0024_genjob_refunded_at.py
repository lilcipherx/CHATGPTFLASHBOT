"""generation_jobs.refunded_at — make charge reversal idempotent at the row

refund_job (credits / image-video-music packs / free Mini App slot) was not
idempotent: the grant/pack-refund branches reversed the charge unconditionally, so
calling refund_job twice on the same job double-credited the user. Every caller
guarded against this by hand (a status re-check before refunding), which is fragile
— one forgotten guard double-refunds.

Add a nullable refunded_at timestamp. refund_job now claims it with a conditional
UPDATE (refunded_at IS NULL); only the first call wins and performs the reversal, so
a credits / pack / free-slot charge comes back at most once across callers, retries,
and concurrency. Stars-paid services (avatar) stay idempotent at the LEDGER instead
(refund_stars_transaction) — the avatar worker bypasses refund_job and does not stamp
this column, so the row-guard covers credits/packs/free, not the Stars path.

No backfill: callers only invoke refund_job at the fail transition (never on an
already-terminal job) and retrying a failed job is blocked, so existing rows leaving
this NULL cannot be re-refunded by current code paths.

Additive + idempotent. Fresh schema is provisioned via create_all, so the column is
added only if absent.

Revision ID: 0024_genjob_refunded_at
Revises: 0023_analytics_window_indexes
Create Date: 2026-06-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_genjob_refunded_at"
down_revision = "0023_analytics_window_indexes"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if "refunded_at" not in _cols("generation_jobs"):
        op.add_column(
            "generation_jobs",
            sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    if "refunded_at" in _cols("generation_jobs"):
        op.drop_column("generation_jobs", "refunded_at")
