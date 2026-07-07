"""Search-model selection: ai_models.search flag + users.search_model choice.

Adds admin control over which models appear in the internet-search (/s) picker
and remembers each user's chosen search model.

- ``ai_models.search`` (bool, default false): the admin flags models that actually
  browse the web (Perplexity Sonar, an OpenAI *-search-preview model, an OpenRouter
  ":online" variant). Only flagged models show in the /s model picker.
- ``users.search_model`` (nullable str): the user's chosen search model key; NULL =
  fall back to the first enabled search model (or Perplexity / the text model).

Both are additive and nullable/defaulted, so the migration is safe on a populated DB.

Revision ID: 0042_search_model
Revises: 0041_paymethod_checkout_cascade
Create Date: 2026-07-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0042_search_model"
down_revision = "0041_paymethod_checkout_cascade"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    # Idempotent: skip a column already present (fresh create_all or partial run).
    if "search" not in _cols("ai_models"):
        op.add_column(
            "ai_models",
            sa.Column("search", sa.Boolean(), nullable=False, server_default="false"),
        )
    if "search_model" not in _cols("users"):
        op.add_column(
            "users",
            sa.Column("search_model", sa.String(length=50), nullable=True),
        )


def downgrade() -> None:
    if "search_model" in _cols("users"):
        op.drop_column("users", "search_model")
    if "search" in _cols("ai_models"):
        op.drop_column("ai_models", "search")
