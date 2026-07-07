"""Zero-infra test setup: SQLite file DB + in-memory Redis, configured BEFORE
any `core.*` import so the cached settings pick them up."""
from __future__ import annotations

import atexit
import os
import tempfile

# Per-PROCESS DB file (PID in the name): multiple pytest runs (e.g. parallel
# worktree agents + a local run) must NOT share one SQLite file, or they trip each
# other's drop_all/create_all with "database is locked" / missing-table errors.
_DB_PATH = os.path.join(tempfile.gettempdir(), f"aibot_test_{os.getpid()}.db")


@atexit.register
def _cleanup_db_file() -> None:
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(_DB_PATH + suffix)
        except OSError:
            pass
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_DB_PATH}")
os.environ.setdefault("REDIS_URL", "memory://")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("BOT_TOKEN", "123:test")

import pytest_asyncio  # noqa: E402 — must follow the env setup above


@pytest_asyncio.fixture(autouse=True)
async def _reset_redis_loop_binding():
    """The fakeredis client is a module singleton; its connection pool binds to the
    event loop of whichever test first touches it. pytest-asyncio gives each test a
    fresh loop, so a later test reusing the pool hits "bound to a different event
    loop". Disconnecting after every test forces a clean rebind on the next use.
    (Now that get_or_create_user reads the live config, most tests touch Redis.)"""
    yield
    try:
        from core.redis_client import redis_client

        await redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001 — best-effort cleanup
        pass
    # Dispose the async engine too: the file-based SQLite engine pools connections
    # that pytest-asyncio's per-test event loop would otherwise leave bound to a
    # dead loop, surfacing as sporadic OperationalError ("database is locked" / loop
    # mismatch) in a later test. Disposing forces a clean reconnect next test.
    try:
        from core.db import engine

        await engine.dispose()
    except Exception:  # noqa: BLE001 — best-effort cleanup
        pass
