"""Regression + guard (Loop L4, findings F2/F3): every index a model declares
(``index=True`` / explicit ``Index``) must actually exist on the ALEMBIC-migrated
schema — the production path — not only on the ``create_all`` model schema the rest of
the suite builds.

Class of bug this guards: a column gets ``index=True`` on the model but no migration
ever creates the index (F2 = ``users.bot_id`` via 0043; F3 = ``gifts.buyer_id`` /
``gifts.redeemed_by`` / ``contest_entries.user_id`` via 0044). ``scripts.check_migrations``
hides it (index-only diffs filtered as SQLite-benign) and ``create_all`` fixtures build
the index straight from the model, so only the alembic path exposes the drift.

This upgrades a fresh SQLite DB through the real migration chain (subprocess — same as
CI's ``alembic upgrade head``) and asserts NO model-declared index is missing.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import sqlalchemy as sa

_REPO = Path(__file__).resolve().parents[1]


def _migrated_indexes() -> dict[str, set[str]]:
    tmp = Path(tempfile.mkdtemp()) / "mig_index_cov.db"
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
        insp = sa.inspect(engine)
        return {t: {ix["name"] for ix in insp.get_indexes(t)} for t in insp.get_table_names()}
    finally:
        engine.dispose()


def test_all_model_declared_indexes_exist_on_migrated_schema() -> None:
    import core.models  # noqa: F401 — register every model on Base.metadata
    from core.models.base import Base

    migrated = _migrated_indexes()
    missing: list[tuple[str, str, list[str]]] = []
    for table in Base.metadata.tables.values():
        if table.name not in migrated:
            missing.append((table.name, "<TABLE MISSING>", []))
            continue
        for idx in table.indexes:
            if idx.name and idx.name not in migrated[table.name]:
                missing.append((table.name, idx.name, [c.name for c in idx.columns]))

    assert not missing, (
        "model declares indexes that no migration creates (they would be absent on a "
        f"real Postgres deploy): {sorted(missing)}"
    )


def test_users_bot_id_indexed_on_migrated_schema() -> None:
    # Explicit anchor for F2 (the finding that surfaced the whole class).
    assert "ix_users_bot_id" in _migrated_indexes().get("users", set())
