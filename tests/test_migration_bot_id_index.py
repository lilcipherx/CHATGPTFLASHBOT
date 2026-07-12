"""Regression (Loop L4, finding F2): ``users.bot_id`` must be indexed on the
ALEMBIC-migrated schema — the production path — not only on the ``create_all`` model
schema the rest of the suite uses.

The model declares ``index=True`` on ``users.bot_id`` (FK ``bot_instances.id`` ON
DELETE SET NULL) for the admin multi-bot dashboard filter (``WHERE bot_id = ?``) and
to avoid a full ``users`` scan on every ``BotInstance`` delete. Migration 0015 added
the column and 0037 added the FK, but no migration ever created the index — so a real
Postgres deploy lacked ``ix_users_bot_id``. ``scripts.check_migrations`` hides this by
filtering index-only diffs as SQLite-benign, and ``create_all``-based test fixtures
build the index straight from the model, so only the alembic path exposes the gap.

This test runs the real migration chain (subprocess, fresh SQLite — same as CI's
``alembic upgrade head``) and asserts the index is present at head.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import sqlalchemy as sa

_REPO = Path(__file__).resolve().parents[1]


def test_users_bot_id_indexed_on_migrated_schema() -> None:
    tmp = Path(tempfile.mkdtemp()) / "mig_bot_id.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{tmp.as_posix()}",
        "REDIS_URL": "memory://",
        "BOT_TOKEN": "123:migtest",
        "ENV": "test",
    }
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"alembic upgrade head failed:\n{proc.stderr}"

    engine = sa.create_engine(f"sqlite:///{tmp.as_posix()}")
    try:
        names = {ix["name"] for ix in sa.inspect(engine).get_indexes("users")}
    finally:
        engine.dispose()

    assert "ix_users_bot_id" in names, (
        "users.bot_id index missing on the alembic-migrated schema "
        f"(model declares index=True); found indexes: {sorted(names)}"
    )
