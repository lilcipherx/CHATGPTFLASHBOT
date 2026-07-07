"""admin controls: carousel banners, user phone/country, per-effect price

Additive schema for the admin-panel expansion:
  * new ``mini_app_banners`` table (Mini App carousel slides)
  * ``users.phone`` + ``users.country`` (captured on contact share)
  * ``price`` override column on both mini_app_*_effects tables

All steps are idempotent — this project provisions a fresh schema via create_all,
so each step only adds what is missing.

Revision ID: 0006_admin_controls
Revises: 0005_rename_diamonds_to_credits
Create Date: 2026-06-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_admin_controls"
down_revision = "0005_rename_diamonds_to_credits"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def _cols(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    return {c["name"] for c in _insp().get_columns(table)}


def upgrade() -> None:
    # 1. carousel banners table
    if not _has_table("mini_app_banners"):
        op.create_table(
            "mini_app_banners",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("image_url", sa.String(length=500), nullable=False),
            sa.Column("title", sa.String(length=120), nullable=True),
            sa.Column("subtitle", sa.String(length=200), nullable=True),
            sa.Column("link_url", sa.String(length=500), nullable=True),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )

    # 2. user phone + country
    have = _cols("users")
    if "phone" not in have:
        op.add_column("users", sa.Column("phone", sa.String(length=20), nullable=True))
    if "country" not in have:
        op.add_column("users", sa.Column("country", sa.String(length=2), nullable=True))

    # 3. per-effect price override
    for table in ("mini_app_photo_effects", "mini_app_video_effects"):
        if "price" not in _cols(table):
            op.add_column(table, sa.Column("price", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    for table in ("mini_app_photo_effects", "mini_app_video_effects"):
        if "price" in _cols(table):
            op.drop_column(table, "price")
    have = _cols("users")
    if "country" in have:
        op.drop_column("users", "country")
    if "phone" in have:
        op.drop_column("users", "phone")
    if _has_table("mini_app_banners"):
        op.drop_table("mini_app_banners")
