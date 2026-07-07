"""Sponsored effects — per-user daily free counter + is_ad on video effects

A sponsored effect (``is_ad``) is promoted (badge + top placement) and FREE for the
user up to an admin-set daily cap (the sponsor pays); past the cap the user pays as
usual. Two additions:
  * ``users.sponsored_free_day`` / ``sponsored_free_date`` — the per-UTC-day counter
    of free sponsored generations a user has used (reset when the date rolls over).
  * ``mini_app_video_effects.is_ad`` — parity with photo effects, so a video effect
    can be sponsored too.

Additive + idempotent; existing rows default to 0 / NULL / false. Fresh schema is
provisioned via create_all, so columns are added only if absent.

Revision ID: 0030_sponsored_effects
Revises: 0029_effect_prompt_mode
Create Date: 2026-06-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_sponsored_effects"
down_revision = "0029_effect_prompt_mode"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    ucols = _cols("users")
    if ucols:
        if "sponsored_free_day" not in ucols:
            op.add_column("users", sa.Column(
                "sponsored_free_day", sa.Integer(), nullable=False, server_default="0"))
        if "sponsored_free_date" not in ucols:
            op.add_column("users", sa.Column(
                "sponsored_free_date", sa.DateTime(timezone=True), nullable=True))
    vcols = _cols("mini_app_video_effects")
    if vcols and "is_ad" not in vcols:
        op.add_column("mini_app_video_effects", sa.Column(
            "is_ad", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    if "is_ad" in _cols("mini_app_video_effects"):
        op.drop_column("mini_app_video_effects", "is_ad")
    ucols = _cols("users")
    if "sponsored_free_date" in ucols:
        op.drop_column("users", "sponsored_free_date")
    if "sponsored_free_day" in ucols:
        op.drop_column("users", "sponsored_free_day")
