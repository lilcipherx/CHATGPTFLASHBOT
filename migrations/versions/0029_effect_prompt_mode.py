"""mini_app_*_effects.prompt_mode — per-effect prompt visibility

Effects range from pure style transforms (img2img, no text needed) to creative
ones (the prompt drives the result). The admin chooses, per effect, how the Mini
App treats the prompt field:
  * ``hidden``   — no prompt field; the saved template is used as-is.
  * ``optional`` — prompt shown, may be left empty (default, current behaviour).
  * ``required`` — prompt shown and must be filled before generating.

Additive + idempotent; existing rows default to ``optional`` (unchanged UX). Fresh
schema is provisioned via create_all, so the column is added only if absent.

Revision ID: 0029_effect_prompt_mode
Revises: 0028_banner_locale
Create Date: 2026-06-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_effect_prompt_mode"
down_revision = "0028_banner_locale"
branch_labels = None
depends_on = None

_TABLES = ("mini_app_photo_effects", "mini_app_video_effects")


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    for table in _TABLES:
        cols = _cols(table)
        if not cols:
            continue  # table provisioned by create_all on a fresh DB
        if "prompt_mode" not in cols:
            op.add_column(
                table,
                sa.Column(
                    "prompt_mode", sa.String(length=10),
                    nullable=False, server_default="optional",
                ),
            )


def downgrade() -> None:
    for table in _TABLES:
        if "prompt_mode" in _cols(table):
            op.drop_column(table, "prompt_mode")
