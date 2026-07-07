"""ai_models.price_in_micros / price_out_micros — per-token model pricing

LLM APIs bill per token (input + output, per 1M tokens), but the catalog only had a
flat per-request cost_micros. Add optional token prices (micro-USD per 1M tokens) so
the admin cost calculator can estimate spend by tokens, not just by request count.
0 = not token-priced (falls back to the per-request cost_micros).

Additive + idempotent, server_default 0 so existing rows backfill to zero. Fresh
schema is provisioned via create_all, so columns are added only if absent.

Revision ID: 0027_ai_model_token_pricing
Revises: 0026_custom_button_stats
Create Date: 2026-06-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_ai_model_token_pricing"
down_revision = "0026_custom_button_stats"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = _cols("ai_models")
    if not cols:
        return
    for col in ("price_in_micros", "price_out_micros"):
        if col not in cols:
            op.add_column("ai_models", sa.Column(col, sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    cols = _cols("ai_models")
    for col in ("price_out_micros", "price_in_micros"):
        if col in cols:
            op.drop_column("ai_models", col)
