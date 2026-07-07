"""Reworked «Обслуживание» page — the Maintenance Center telemetry + safe ops
behind it (no migration):

  * GET  /maintenance/overview        — system snapshot (DB/disk/Redis/counts).
  * GET  /maintenance/database        — per-table row counts + SQLite page stats.
  * POST /maintenance/database/{op}   — VACUUM/ANALYZE/REINDEX/OPTIMIZE/integrity.
  * GET  /maintenance/storage         — media category sizes (local backend).
  * GET  /maintenance/cache           — Redis stats + app-cache key count.
  * POST /maintenance/cache/flush     — clear ONLY rebuildable app caches.

Calls the endpoint coroutines directly against the seeded SQLite + fakeredis test
stack (no HTTP), mirroring tests/test_localization.py.
"""
from __future__ import annotations

import pytest_asyncio

from api.admin import maintenance
from core.db import SessionFactory, engine
from core.models import Base, GenerationJob, User
from core.redis_client import redis_client


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


class _Admin:
    id = 1


class _Req:
    client = None


async def _seed(users: int = 3, jobs: int = 2) -> None:
    async with SessionFactory() as s:
        for i in range(users):
            s.add(User(user_id=1000 + i))
        for _ in range(jobs):
            s.add(GenerationJob(user_id=1000, service="chat", status="complete"))
        await s.commit()


# ---- overview --------------------------------------------------------------
async def test_overview_real_snapshot():
    await _seed(users=4, jobs=3)
    async with SessionFactory() as s:
        out = await maintenance.maintenance_overview(admin=_Admin(), session=s)

    assert out["engine"] == "sqlite"
    assert out["db"]["size_bytes"] > 0
    assert out["db"]["page_size"] > 0
    assert out["counts"]["users"] == 4
    assert out["counts"]["jobs_total"] == 3
    assert out["counts"]["jobs_by_status"]["complete"] == 3
    # disk usage comes from shutil — a real volume always has a non-zero total.
    assert out["disk"]["total_bytes"] > 0
    # Redis probe degrades gracefully where INFO is unavailable (fakeredis): the
    # snapshot still renders with ok=False rather than raising. Real Redis → True.
    assert isinstance(out["redis"]["ok"], bool)
    assert out["storage_backend"] in ("local", "s3")
    assert out["uptime_seconds"] >= 0


# ---- database --------------------------------------------------------------
async def test_database_lists_tables_with_counts():
    await _seed(users=5, jobs=0)
    async with SessionFactory() as s:
        out = await maintenance.database_stats(admin=_Admin(), session=s)
    by_name = {t["name"]: t for t in out["tables"]}
    assert "users" in by_name
    assert by_name["users"]["rows"] == 5
    assert out["engine"] == "sqlite"
    assert out["page"]["page_count"] > 0
    # tables are sorted by row count desc — users (5) should outrank empty tables.
    assert out["tables"][0]["rows"] >= out["tables"][-1]["rows"]


# ---- db maintenance ops ----------------------------------------------------
async def test_db_op_integrity_check_ok():
    await _seed()
    async with SessionFactory() as s:
        out = await maintenance.run_db_maintenance(
            "integrity_check", _Req(), admin=_Admin(), session=s)
    assert out["ok"] is True
    assert out["result"] == "ok"


async def test_db_op_vacuum_runs_outside_transaction():
    await _seed(users=10, jobs=10)
    # VACUUM must execute outside an open transaction (AUTOCOMMIT connection).
    async with SessionFactory() as s:
        out = await maintenance.run_db_maintenance("vacuum", _Req(), admin=_Admin(), session=s)
    assert out["ok"] is True
    assert out["op"] == "vacuum"
    assert out["size_after"] > 0


async def test_db_op_analyze_and_optimize():
    await _seed()
    for op in ("analyze", "optimize", "reindex"):
        async with SessionFactory() as s:
            out = await maintenance.run_db_maintenance(op, _Req(), admin=_Admin(), session=s)
        assert out["ok"] is True


async def test_db_op_unknown_rejected():
    import pytest
    from fastapi import HTTPException

    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await maintenance.run_db_maintenance("drop_all", _Req(), admin=_Admin(), session=s)
    assert ei.value.status_code == 400


# ---- storage ---------------------------------------------------------------
async def test_storage_local_backend():
    async with SessionFactory() as s:
        out = await maintenance.storage_stats(admin=_Admin(), session=s)
    # No S3 configured in tests → local backend with a category list (possibly empty).
    assert out["backend"] == "local"
    assert isinstance(out["categories"], list)
    assert "total_bytes" in out


# ---- cache -----------------------------------------------------------------
async def test_cache_flush_clears_only_app_prefixes():
    # Seed one rebuildable app-cache key and one protected runtime key.
    await redis_client.set("cache:dummy", "x")
    await redis_client.set("admin:dashboard:v1", "{}")
    await redis_client.set("fsm:user:123", "keep-me")

    async with SessionFactory() as s:
        stats = await maintenance.cache_stats(admin=_Admin())
        assert stats["app_cache_keys"] >= 2
        out = await maintenance.cache_flush(_Req(), admin=_Admin(), session=s)

    assert out["ok"] is True
    assert out["deleted"] >= 2
    # The protected runtime key is untouched (never FLUSHALL).
    assert await redis_client.get("fsm:user:123") == "keep-me"
    assert await redis_client.get("cache:dummy") is None
