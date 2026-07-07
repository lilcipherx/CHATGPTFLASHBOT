"""AUDIT-SCHED - admin-controllable scheduled jobs.

Adds the ``cron_jobs`` table backing core.services.cron_control: one row per beat
cron job with an ``enabled`` flag and an ``interval_seconds`` cadence, both editable
from the admin panel at runtime. Rows are auto-created by the app (cron_control) with
sensible defaults, so no data seeding is required here.

Revision ID: 0040_cron_jobs
Revises: 0039_admin_backup_codes
Create Date: 2026-07-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0040_cron_jobs"
down_revision = "0039_admin_backup_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cron_jobs",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), server_default="3600", nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("cron_jobs")
