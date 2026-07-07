"""FIX: AUDIT13-H3 - add ON DELETE CASCADE FKs for payment_methods + checkout_intents.

The 2026-07-06 audit found these two user-data tables were missing from the 0038
cascade set: `payment_methods.user_id` (saved recurring-payment tokens) and
`checkout_intents.user_id` (abandoned-cart rows) had NO FK to `users.user_id` and
were not covered by `delete_user_data()`. Deleting a User orphaned live billing
tokens + cart rows — a GDPR Art.17 right-to-erasure gap.

`delete_user_data()` now deletes both tables explicitly (for counts + SQLite dev,
where cascade FKs are not created); this migration adds the DB-level CASCADE FK as
defense-in-depth so a raw `DELETE FROM users` also cascades.

Mirrors 0038's safe pattern: on Postgres each FK is added `NOT VALID` (brief
ACCESS EXCLUSIVE, no row scan) in its own autocommit block, then `VALIDATE
CONSTRAINT` separately (SHARE UPDATE EXCLUSIVE — reads+writes continue). Non-Postgres
falls back to plain create_foreign_key (best effort).

Revision ID: 0041_paymethod_checkout_cascade
Revises: 0040_cron_jobs
Create Date: 2026-07-06
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0041_paymethod_checkout_cascade"
down_revision = "0040_cron_jobs"
branch_labels = None
depends_on = None


_CASCADE_FKS = [
    ("payment_methods",  "fk_payment_methods_user_id"),
    ("checkout_intents", "fk_checkout_intents_user_id"),
]


def upgrade() -> None:
    # Drop any pre-existing orphan rows so the FK can be added without a violation.
    for tbl, _name in _CASCADE_FKS:
        try:
            op.execute(
                f"DELETE FROM {tbl} WHERE user_id IS NOT NULL "
                f"AND user_id NOT IN (SELECT user_id FROM users)"
            )
        except Exception:  # noqa: BLE001 - table may not exist in some installs
            pass

    if op.get_bind().dialect.name == "postgresql":
        # Phase 1: add each FK as NOT VALID (fast, brief lock), own autocommit block.
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
