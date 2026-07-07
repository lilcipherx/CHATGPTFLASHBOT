"""routing multimodal: per-model backend pin (ai_models.account_kind)

Adds an optional ``account_kind`` to ai_models so the admin can route a single
model through a specific backend kind (omniroute / apimart / kie / direct …)
instead of just "any account of this modality". NULL keeps the current behaviour,
so this migration is fully backward-compatible (no behaviour change until an
admin sets a value).

Revision ID: 0003_routing_multimodal
Revises: 0002_effect_presets
Create Date: 2026-06-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_routing_multimodal"
down_revision = "0002_effect_presets"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    # Idempotent: 0000 baseline builds ai_models via create_all on fresh DBs, so
    # the column may already exist there; only add it when missing.
    if not _has_column("ai_models", "account_kind"):
        op.add_column(
            "ai_models",
            sa.Column("account_kind", sa.String(length=20), nullable=True),
        )


def downgrade() -> None:
    if _has_column("ai_models", "account_kind"):
        op.drop_column("ai_models", "account_kind")
