"""mini_app_banners.locale — per-language carousel targeting

Carousel slide images carry baked-in text, so the admin localizes the carousel by
making a per-language slide rather than translating an overlay. Add a nullable
``locale`` column: NULL = shown to every language (back-compat for existing slides),
a 2-letter code = shown only to users on that language. The Mini App passes its
locale to /api/banners and the endpoint filters NULL-or-matching slides.

Additive + idempotent; existing rows keep locale = NULL (shown to all). Fresh schema
is provisioned via create_all, so the column is added only if absent.

Revision ID: 0028_banner_locale
Revises: 0027_ai_model_token_pricing
Create Date: 2026-06-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028_banner_locale"
down_revision = "0027_ai_model_token_pricing"
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
    if "locale" not in cols:
        op.add_column(
            "mini_app_banners",
            sa.Column("locale", sa.String(length=8), nullable=True),
        )


def downgrade() -> None:
    if "locale" in _cols("mini_app_banners"):
        op.drop_column("mini_app_banners", "locale")
