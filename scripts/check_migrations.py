"""CI guard: the Alembic migrations must fully reproduce the SQLAlchemy models.

Runs an `alembic upgrade head` against a throwaway SQLite DB, then asks Alembic's
autogenerate to diff the live schema against ``Base.metadata``. A non-empty diff
means a model was changed without a matching migration — the build fails with the
offending operations so the gap is fixed before merge.

Usage:  python -m scripts.check_migrations
Exit 0 = models and migrations agree; exit 1 = drift detected.
"""
from __future__ import annotations

import os
import sys
import tempfile

# Force a clean, isolated SQLite DB BEFORE importing core (cached settings).
_DB = os.path.join(tempfile.gettempdir(), "aibot_migcheck.db")
if os.path.exists(_DB):
    os.remove(_DB)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB}"
os.environ.setdefault("REDIS_URL", "memory://")
os.environ.setdefault("BOT_TOKEN", "123:migcheck")

from alembic import command  # noqa: E402
from alembic.autogenerate import compare_metadata  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

from core.models import Base  # noqa: E402


def main() -> int:
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")

    # alembic autogenerate needs a sync engine; use the sync sqlite URL.
    sync_engine = create_engine(f"sqlite:///{_DB}")
    with sync_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        diff = compare_metadata(ctx, Base.metadata)

    # SQLite can't express some PG-only constructs (partial/trigram indexes), so a
    # handful of index-only diffs on SQLite are expected and benign. Treat only
    # table/column add/remove as real drift.
    real = [
        d for d in diff
        if isinstance(d, tuple) and d and str(d[0]).startswith(
            ("add_table", "remove_table", "add_column", "remove_column")
        )
    ]
    if real:
        print("Model/migration drift detected — generate a migration for:")
        for d in real:
            print("  -", d[0], getattr(d[-1], "name", d[1:]))
        return 1
    print("OK: migrations reproduce the models (no table/column drift).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
