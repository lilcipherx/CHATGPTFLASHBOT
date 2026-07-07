"""search + generation-job indexes

Scale hardening for two hot paths:

  * Admin user search uses ``username``/``phone`` ILIKE '%q%'. A plain B-tree can't
    serve a leading-wildcard LIKE, so on Postgres we add the ``pg_trgm`` extension
    and GIN trigram indexes — turning the seq scan into an index scan at millions
    of users. (SQLite dev/test has no pg_trgm; the search still works there via a
    table scan, which is fine at dev scale, so these are Postgres-only.)

  * ``generation_jobs`` gets two composite indexes matching the Mini App
    history/refund queries (user_id, service, created_at) and the stuck-job sweep
    (status, created_at). These mirror the model ``__table_args__`` so a fresh
    create_all dev DB already has them; this migration adds them to existing DBs.

All steps are idempotent (IF NOT EXISTS / introspection guard) so re-running or
running after a create_all is a no-op.

Revision ID: 0007_search_job_indexes
Revises: 0006_admin_controls
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_search_job_indexes"
down_revision = "0006_admin_controls"
branch_labels = None
depends_on = None


def _has_index(table: str, name: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return any(ix["name"] == name for ix in insp.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()

    # FIX: C4 - CONCURRENTLY cannot run inside a transaction; use autocommit_block
    # on Postgres so the migration doesn't fail. SQLite ignores the kwarg entirely.
    if not _has_index("generation_jobs", "ix_genjobs_user_service_created"):
        with op.get_context().autocommit_block():
            op.create_index(
                "ix_genjobs_user_service_created",
                "generation_jobs",
                ["user_id", "service", "created_at"],
                postgresql_concurrently=True,
            )
    if not _has_index("generation_jobs", "ix_genjobs_status_created"):
        with op.get_context().autocommit_block():
            op.create_index(
                "ix_genjobs_status_created",
                "generation_jobs",
                ["status", "created_at"],
                postgresql_concurrently=True,
            )

    # Trigram search indexes — Postgres only.
    # FIX: F50 - the CREATE EXTENSION pg_trgm below requires Postgres superuser on
    # managed Postgres (RDS/Cloud SQL/Aurora). Operators on those platforms must
    # pre-install the extension out-of-band (via the cloud provider's superuser
    # role) before running this migration; the CREATE EXTENSION here will fail
    # otherwise. Documented in DEPLOYMENT.md / docs/DEPLOYMENT.md.
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        # FIX: AUDIT-H6 - build the GIN indexes CONCURRENTLY so the CREATE doesn't take
        # a SHARE lock that blocks every write on `users` for the whole (multi-minute)
        # build. CONCURRENTLY cannot run inside a transaction → autocommit_block.
        if not _has_index("users", "ix_users_username_trgm"):
            with op.get_context().autocommit_block():
                op.execute(
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_username_trgm "
                    "ON users USING gin (username gin_trgm_ops)"
                )
        if not _has_index("users", "ix_users_phone_trgm"):
            with op.get_context().autocommit_block():
                op.execute(
                    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_phone_trgm "
                    "ON users USING gin (phone gin_trgm_ops)"
                )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # FIX: AUDIT-H6 - drop CONCURRENTLY too (matches the concurrent create; avoids
        # an ACCESS EXCLUSIVE lock on `users`).
        with op.get_context().autocommit_block():
            op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_users_phone_trgm")
        with op.get_context().autocommit_block():
            op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_users_username_trgm")
    if _has_index("generation_jobs", "ix_genjobs_status_created"):
        op.drop_index("ix_genjobs_status_created", table_name="generation_jobs")
    if _has_index("generation_jobs", "ix_genjobs_user_service_created"):
        op.drop_index("ix_genjobs_user_service_created", table_name="generation_jobs")
