"""custom_button_stats — click tracking for /links buttons

The admin /links buttons live in business_config.custom_buttons (a JSON list). To
give the panel a real "clicks" number instead of a placeholder, the bot renders each
button through a /r/{id} redirect (only when a public base URL is configured) that
logs a tap here, then 302s to the live URL. This table is a lightweight per-button
counter keyed by the button's stable id; the URL itself is never duplicated here (it
is read live from the config at redirect time).

Additive: a fresh table created only when absent. Fresh schema is provisioned via
create_all, so this is a no-op there.

Revision ID: 0026_custom_button_stats
Revises: 0025_banner_engagement_counters
Create Date: 2026-06-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_custom_button_stats"
down_revision = "0025_banner_engagement_counters"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "custom_button_stats" not in _tables():
        op.create_table(
            "custom_button_stats",
            sa.Column("button_id", sa.String(length=64), primary_key=True),
            sa.Column("clicks", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("last_click_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    if "custom_button_stats" in _tables():
        op.drop_table("custom_button_stats")
