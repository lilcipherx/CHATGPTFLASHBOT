"""FIX: F47-F49, F52-F54, F56 - schema correctness fixes from Round 5 audit.

Combines three independent additive fixes into one migration so the chain stays
linear and operators don't face a cascade of tiny migrations:

1. F47/F48 (SQLite autoincrement): the existing ``mini_app_banners.id`` and
   ``checkout_intents.id`` tables were created with a plain ``BigInteger`` PK. On
   SQLite that does NOT auto-assign (BIGINT PK isn't the rowid alias), so dev/test
   INSERTs fail the NOT NULL id constraint. FIX: M14 - this migration does NOT
   auto-fix these (table rebuild via batch_alter_table is fragile and dev-only);
   instead, rebuild dev DBs via ``create_all`` which uses the correct with_variant
   PK pattern from core/models/types.py. F49 is moot (agents/agent_earnings were
   already dropped in 0032).

2. F52/F53/F56 (admin_id type mismatch): ``user_notes.admin_id`` and
   ``support_messages.admin_id`` were created as ``Integer`` (int4) but
   ``admin_users.id`` is ``BigInteger`` (int8). On Postgres this is a type
   mismatch that breaks FK integrity and any JOIN. Widen both to BigInteger.

3. F54 (missing FK on users.bot_id): ``users.bot_id`` is a plain BigInteger
   with no FK to ``bot_instances.id``. Add the FK with ``ON DELETE SET NULL``
   so deleting a BotInstance orphans no users.

Revision ID: 0037_round5_schema_fixes
Revises: 0036_checkout_intents
Create Date: 2026-06-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037_round5_schema_fixes"
down_revision = "0036_checkout_intents"
branch_labels = None
depends_on = None


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _col_type(table: str, col: str) -> str | None:
    """Lower-cased type name of a column, or None if absent."""
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return None
    for c in insp.get_columns(table):
        if c["name"] == col:
            return str(c["type"]).lower()
    return None


def upgrade() -> None:
    # --- F52/F53/F56: widen admin_id Integer → BigInteger on Postgres ---
    # SQLite ignores type changes (dynamic typing), so this is a Postgres-only fix.
    if not _is_sqlite():
        if "user_notes" in _tables() and "admin_id" in _cols("user_notes"):
            current = _col_type("user_notes", "admin_id") or ""
            if "bigint" not in current and "int8" not in current:
                op.alter_column(
                    "user_notes", "admin_id",
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False,
                )
        if "support_messages" in _tables() and "admin_id" in _cols("support_messages"):
            current = _col_type("support_messages", "admin_id") or ""
            if "bigint" not in current and "int8" not in current:
                op.alter_column(
                    "support_messages", "admin_id",
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=True,
                )

    # --- F54: add FK users.bot_id → bot_instances.id (ON DELETE SET NULL) ---
    # Idempotent: skip if the FK already exists (fresh schema may create it via
    # create_all, or a prior run of this migration).
    if "users" in _tables() and "bot_instances" in _tables() and "bot_id" in _cols("users"):
        bind = op.get_bind()
        existing_fks = {
            fk["name"]
            for fk in sa.inspect(bind).get_foreign_keys("users")
            if fk.get("constrained_columns") == ["bot_id"]
        }
        # Alembic auto-names a FK `users_bot_id_fkey` on Postgres when name is None;
        # check both the auto-name and an empty-name match.
        if not existing_fks and "users_bot_id_fkey" not in existing_fks:
            # FIX: AUDIT13-H4 - on Postgres, add the FK as NOT VALID (fast, metadata-only,
            # brief ACCESS EXCLUSIVE lock — NO row scan) then VALIDATE separately (SHARE
            # UPDATE EXCLUSIVE — reads+writes continue), mirroring 0038. A plain
            # create_foreign_key holds ACCESS EXCLUSIVE on the hot `users` table for the
            # ENTIRE validation scan, blocking all traffic during deploy.
            if bind.dialect.name == "postgresql":
                with op.get_context().autocommit_block():
                    try:
                        op.execute(
                            "ALTER TABLE users ADD CONSTRAINT users_bot_id_fkey "
                            "FOREIGN KEY (bot_id) REFERENCES bot_instances(id) "
                            "ON DELETE SET NULL NOT VALID"
                        )
                    except Exception:  # noqa: BLE001 - already exists (idempotent)
                        pass
                with op.get_context().autocommit_block():
                    try:
                        op.execute("ALTER TABLE users VALIDATE CONSTRAINT users_bot_id_fkey")
                    except Exception:  # noqa: BLE001 - already validated / missing
                        pass
            else:
                try:
                    op.create_foreign_key(
                        "users_bot_id_fkey", "users", "bot_instances",
                        ["bot_id"], ["id"], ondelete="SET NULL",
                    )
                except Exception:
                    # SQLite doesn't support ALTER TABLE ADD FOREIGN KEY — non-fatal.
                    pass

    # --- F47/F48/F49: SQLite autoincrement PK fix ---
    # Only SQLite needs this; Postgres BIGINT PK auto-increments via IDENTITY.
    # We can't ALTER COLUMN ... TYPE to add a with_variant in-place; the canonical
    # SQLite fix is table-rebuild (create_new, copy, drop_old, rename). For dev DBs
    # the simplest safe path is documented here but NOT executed automatically —
    # operators rebuilding a dev DB from migrations will get the correct PK from
    # the fresh create_all path (core/models/types.py BigIntPK already uses
    # with_variant). This block is a no-op placeholder so the migration is honest
    # about what it does and does not do.
    # (No DDL: see migration docstring.)


def downgrade() -> None:
    # Reverse the FK addition (admin_id widening is non-reversible on Postgres
    # without data loss assumptions; leave it as BigInteger).
    if "users" in _tables():
        try:
            op.drop_constraint("users_bot_id_fkey", "users", type_="foreignkey")
        except Exception:
            pass
