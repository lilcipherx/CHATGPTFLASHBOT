"""FIX: AUDIT12-36 - add admin_users.backup_codes_hashed for 2FA recovery codes.

The audit found that admin 2FA had no recovery path: an admin who lost their
TOTP device was permanently locked out (only a superadmin DB intervention
could restore access). This migration adds a JSONB column to store 8 argon2-
hashed single-use backup codes per admin, generated at 2FA-enrolment time and
returned to the admin UI ONCE in plaintext (see core.services.admin_auth.enable_2fa).

The column is nullable (existing admins have no backup codes until they re-enroll
in 2FA) and defaults to an empty list. Only the *hashes* are stored so a DB leak
doesn't expose recovery codes; each consumed code is removed server-side after a
successful login (one-time use).

Revision ID: 0039_admin_backup_codes
Revises: 0038_user_cascade_delete
Create Date: 2026-06-30
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "0039_admin_backup_codes"
down_revision = "0038_user_cascade_delete"
branch_labels = None
depends_on = None


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    # Idempotent: skip if the column was already added (fresh schema via
    # create_all, or a prior partial run).
    if "backup_codes_hashed" in _cols("admin_users"):
        return
    # JSONB on Postgres (indexable, binary, no key-order ambiguity); plain JSON
    # on SQLite (dev/test). Both store a list[str] of argon2 hashes.
    if _is_sqlite():
        col_type = sa.JSON()
    else:
        col_type = JSONB()
    op.add_column(
        "admin_users",
        sa.Column(
            "backup_codes_hashed",
            col_type,
            nullable=True,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    if "backup_codes_hashed" in _cols("admin_users"):
        op.drop_column("admin_users", "backup_codes_hashed")
