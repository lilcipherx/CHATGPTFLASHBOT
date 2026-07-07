"""Result retention (ТЗ §5): cron prunes old artifacts; 0 days = keep forever.

Seeds GenerationJobs / GalleryItems with old + recent created_at and asserts the
prune helpers (and run_retention) drop only what the window permits.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import func, select

from core.db import SessionFactory, engine
from core.models import Base, GalleryItem, GenerationJob
from core.services import pricing
from core.services.retention import prune_gallery, prune_jobs, run_retention

OLD = datetime.now(UTC) - timedelta(days=60)
RECENT = datetime.now(UTC) - timedelta(days=1)


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield
    try:
        await pricing.redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


def _job(status: str, created_at: datetime) -> GenerationJob:
    return GenerationJob(
        user_id=1, service="image", status=status, created_at=created_at
    )


def _item(status: str, created_at: datetime) -> GalleryItem:
    return GalleryItem(
        user_id=1, image_url="http://x/y.png", status=status, created_at=created_at
    )


async def _count(session, model) -> int:
    return await session.scalar(select(func.count()).select_from(model))


async def _seed_jobs(session):
    session.add_all([
        _job("complete", OLD),        # prunable (real worker success status)
        _job("failed", OLD),          # prunable
        _job("complete", RECENT),     # too recent — keep
        _job("pending", OLD),         # non-terminal — keep
        _job("processing", OLD),      # non-terminal — keep
    ])
    await session.commit()


async def test_prune_jobs_removes_only_old_terminal():
    async with SessionFactory() as s:
        await _seed_jobs(s)
    async with SessionFactory() as s:
        removed = await prune_jobs(s, job_days=30)
        assert removed == 2  # the two old terminal jobs only
        assert await _count(s, GenerationJob) == 3
        kept = (await s.scalars(select(GenerationJob.status))).all()
        assert sorted(kept) == ["complete", "pending", "processing"]


async def test_prune_jobs_zero_is_noop():
    async with SessionFactory() as s:
        await _seed_jobs(s)
    async with SessionFactory() as s:
        assert await prune_jobs(s, job_days=0) == 0
        assert await _count(s, GenerationJob) == 5


async def test_prune_gallery_removes_old_any_status():
    async with SessionFactory() as s:
        s.add_all([
            _item("approved", OLD),
            _item("rejected", OLD),
            _item("pending", RECENT),
        ])
        await s.commit()
    async with SessionFactory() as s:
        removed = await prune_gallery(s, gallery_days=30)
        assert removed == 2
        assert await _count(s, GalleryItem) == 1


async def test_run_retention_default_keeps_items_within_window():
    # Prod defaults are job_days=90 / gallery_days=180; OLD=60d falls within both, so a
    # default run keeps everything (nothing is yet old enough to prune).
    async with SessionFactory() as s:
        await _seed_jobs(s)
        s.add(_item("approved", OLD))
        await s.commit()
    async with SessionFactory() as s:
        res = await run_retention(s)
        assert res == {"jobs_pruned": 0, "gallery_pruned": 0, "intents_pruned": 0}
        assert await _count(s, GenerationJob) == 5
        assert await _count(s, GalleryItem) == 1


async def test_run_retention_default_prunes_beyond_window():
    # Past the default windows (>90d jobs / >180d gallery) the default run prunes.
    very_old_job = datetime.now(UTC) - timedelta(days=100)
    very_old_item = datetime.now(UTC) - timedelta(days=200)
    async with SessionFactory() as s:
        s.add_all([_job("complete", very_old_job), _item("approved", very_old_item)])
        await s.commit()
    async with SessionFactory() as s:
        res = await run_retention(s)
        assert res["jobs_pruned"] == 1 and res["gallery_pruned"] == 1
        assert await _count(s, GenerationJob) == 0
        assert await _count(s, GalleryItem) == 0


async def test_prune_jobs_drops_our_stored_media(tmp_path, monkeypatch):
    # A pruned job's re-hosted /media file is deleted from storage; an external provider
    # URL is left untouched.
    from core.services import storage

    monkeypatch.setattr(storage, "_MEDIA_ROOT", str(tmp_path))
    ours = tmp_path / "results" / "x.png"
    ours.parent.mkdir(parents=True)
    ours.write_bytes(b"img")
    old = datetime.now(UTC) - timedelta(days=100)
    async with SessionFactory() as s:
        s.add_all([
            GenerationJob(user_id=1, service="image", status="complete",
                          created_at=old, result_url="/media/results/x.png"),
            GenerationJob(user_id=1, service="image", status="complete",
                          created_at=old, result_url="https://provider.example/y.png"),
        ])
        await s.commit()
        removed = await prune_jobs(s, job_days=90)
    assert removed == 2
    assert not ours.exists()  # our stored file was cleaned up


async def test_run_retention_with_override_prunes():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"retention": {"job_days": 30, "gallery_days": 30}})
    async with SessionFactory() as s:
        await _seed_jobs(s)
        s.add_all([_item("approved", OLD), _item("pending", RECENT)])
        await s.commit()
    async with SessionFactory() as s:
        res = await run_retention(s)
        assert res == {"jobs_pruned": 2, "gallery_pruned": 1, "intents_pruned": 0}
        assert await _count(s, GenerationJob) == 3
        assert await _count(s, GalleryItem) == 1
