"""mini_app_banners.impressions / clicks — real carousel engagement tracking

The admin carousel page showed a placeholder "Показы / CTR" KPI because there was
no tracking. Rather than a heavy per-event table, add two lightweight counters on
the banner row: the Mini App increments ``impressions`` when a slide is shown and
``clicks`` when it is tapped (via /api/banners/{id}/impression|click), and the admin
derives CTR = clicks / impressions. Totals only (no time-series) — sufficient for the
per-slide CTR and the aggregate KPI, and cheap (one atomic UPDATE per event).

Additive + idempotent with a server_default of 0 so existing rows backfill to zero.
Fresh schema is provisioned via create_all, so columns are added only if absent.

Revision ID: 0025_banner_engagement_counters
Revises: 0024_genjob_refunded_at
Create Date: 2026-06-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_banner_engagement_counters"
down_revision = "0024_genjob_refunded_at"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = _cols("mini_app_banners")
    if not cols:
        return  # table provisioned by create_all on a fresh DB
    if "impressions" not in cols:
        op.add_column(
            "mini_app_banners",
            sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        )
    if "clicks" not in cols:
        op.add_column(
            "mini_app_banners",
            sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    cols = _cols("mini_app_banners")
    if "clicks" in cols:
        op.drop_column("mini_app_banners", "clicks")
    if "impressions" in cols:
        op.drop_column("mini_app_banners", "impressions")
