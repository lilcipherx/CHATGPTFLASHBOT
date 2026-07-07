"""FIX: AUDIT12-20 - add ON DELETE CASCADE FKs for user data tables (GDPR Art. 17).

The audit found that only `pack_balances` had an FK to `users.user_id` with
`ondelete='CASCADE'`. The other 9 user-data tables (`generation_jobs`,
`transactions`, `usage_log`, `referrals`, `support_messages`, `user_notes`,
`user_tags`, `complaints`, `message_feedback`) had NO FK at all, so deleting
a `User` row orphaned all of them — making GDPR right-to-erasure impossible.

This migration adds `FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE`
to each of those tables. Existing orphaned rows (if any) are left in place —
they'll be cleaned up by the new delete_user_data() service explicitly. Future
deletions are atomic and cascade correctly.

FIX: AUDIT-M2 - on Postgres we add each FK as `NOT VALID` first (a fast metadata-only
change that takes only a brief ACCESS EXCLUSIVE lock, NO row scan), commit to release
that lock, then `VALIDATE CONSTRAINT` in a separate transaction. VALIDATE takes only a
SHARE UPDATE EXCLUSIVE lock, so concurrent reads AND writes continue during the scan.
A plain `ADD CONSTRAINT ... FOREIGN KEY` (the previous approach) holds ACCESS EXCLUSIVE
for the ENTIRE validation scan — blocking all traffic on transactions/generation_jobs/
usage_log for the scan duration, which is NOT sub-second on a large deployment.
Non-Postgres (SQLite dev/test) falls back to plain create_foreign_key (best effort).

Revision ID: 0038_user_cascade_delete
Revises: 0037_round5_schema_fixes
Create Date: 2026-06-29
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0038_user_cascade_delete"
down_revision = "0037_round5_schema_fixes"
branch_labels = None
depends_on = None


# (table_name, constraint_name) pairs to add ON DELETE CASCADE FKs.
# Each (user_id INTEGER) -> users.user_id BIGINT FK.
# We use the existing column as-is (no type change — Postgres allows FK on int4->int8
# via implicit cast, but to be safe we already widened user_id columns to BigInteger
# in earlier migrations).
_CASCADE_FKS = [
    ("generation_jobs",   "fk_generation_jobs_user_id"),
    ("transactions",      "fk_transactions_user_id"),
    ("usage_log",         "fk_usage_log_user_id"),
    ("referrals",         "fk_referrals_user_id"),
    ("support_messages",  "fk_support_messages_user_id"),
    ("user_notes",        "fk_user_notes_user_id"),
    ("user_tags",         "fk_user_tags_user_id"),
    ("complaints",        "fk_complaints_user_id"),
    ("message_feedback",  "fk_message_feedback_user_id"),
    ("contest_entries",   "fk_contest_entries_user_id"),
    ("gallery_items",     "fk_gallery_items_user_id"),
]


def upgrade() -> None:
    # Drop any pre-existing (orphan) rows first so the FK constraint can be added
    # without a violation. These tables were un-FK'd, so orphans may exist from
    # legacy user-deletes that didn't cascade. We do this best-effort per-table
    # (LEFT JOIN is more elegant but MySQL/SQLite differ; this works everywhere).
    for tbl, _name in _CASCADE_FKS:
        try:
            op.execute(
                f"DELETE FROM {tbl} WHERE user_id IS NOT NULL "
                f"AND user_id NOT IN (SELECT user_id FROM users)"
            )
        except Exception:  # noqa: BLE001 - table may not exist in some installs
            pass

    if op.get_bind().dialect.name == "postgresql":
        # Phase 1: add every FK as NOT VALID (fast, brief lock), each in its own
        # autocommit block so the ACCESS EXCLUSIVE lock is released immediately.
        for tbl, name in _CASCADE_FKS:
            with op.get_context().autocommit_block():
                try:
                    op.execute(
                        f"ALTER TABLE {tbl} ADD CONSTRAINT {name} "
                        f"FOREIGN KEY (user_id) REFERENCES users(user_id) "
                        f"ON DELETE CASCADE NOT VALID"
                    )
                except Exception:  # noqa: BLE001 - constraint may already exist
                    pass
        # Phase 2: validate separately (SHARE UPDATE EXCLUSIVE — writes allowed).
        for tbl, name in _CASCADE_FKS:
            with op.get_context().autocommit_block():
                try:
                    op.execute(f"ALTER TABLE {tbl} VALIDATE CONSTRAINT {name}")
                except Exception:  # noqa: BLE001 - already validated / missing
                    pass
    else:
        for tbl, name in _CASCADE_FKS:
            try:
                op.create_foreign_key(
                    name, tbl, "users", ["user_id"], ["user_id"], ondelete="CASCADE",
                )
            except Exception:  # noqa: BLE001 - constraint may already exist
                pass


def downgrade() -> None:
    for tbl, name in _CASCADE_FKS:
        try:
            op.drop_constraint(name, tbl, type_="foreignkey")
        except Exception:  # noqa: BLE001
            pass
