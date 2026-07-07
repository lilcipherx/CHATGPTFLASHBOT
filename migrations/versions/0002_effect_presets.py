"""effect presets: extend mini_app_*_effects into Higgsfield-style presets

Additive columns on the existing photo/video effect tables so each row becomes a
style preset (recommended/compatible models, hidden prompt template, default
params, multi-photo limit, preview, trending/enabled flags, author, ordering).

Revision ID: 0002_effect_presets
Revises: 0001_ai_routing
Create Date: 2026-06-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_effect_presets"
down_revision = "0001_ai_routing"
branch_labels = None
depends_on = None

_NEW_COLUMNS = [
    ("recommended_model", lambda: sa.Column("recommended_model", sa.String(length=40), nullable=True)),
    ("compatible_models", lambda: sa.Column("compatible_models", sa.JSON(), nullable=True)),
    ("prompt_template", lambda: sa.Column("prompt_template", sa.Text(), nullable=True)),
    ("default_params", lambda: sa.Column("default_params", sa.JSON(), nullable=True)),
    ("max_photos", lambda: sa.Column("max_photos", sa.Integer(), server_default="1", nullable=False)),
    ("preview_url", lambda: sa.Column("preview_url", sa.String(length=500), nullable=True)),
    ("is_trending", lambda: sa.Column("is_trending", sa.Boolean(), server_default=sa.false(), nullable=False)),
    ("enabled", lambda: sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False)),
    ("author", lambda: sa.Column("author", sa.String(length=40), nullable=True)),
    ("sort_order", lambda: sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False)),
]

_TABLES = ("mini_app_photo_effects", "mini_app_video_effects")


def _existing(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    # Idempotent: this project provisions the base schema via create_all (which
    # already builds the new columns on a fresh DB), so only add what's missing.
    for table in _TABLES:
        have = _existing(table)
        for name, make_col in _NEW_COLUMNS:
            if name not in have:
                op.add_column(table, make_col())


def downgrade() -> None:
    for table in _TABLES:
        have = _existing(table)
        for name, _make_col in reversed(_NEW_COLUMNS):
            if name in have:
                op.drop_column(table, name)
