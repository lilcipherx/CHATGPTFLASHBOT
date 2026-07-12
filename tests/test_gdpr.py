"""GDPR Art.17 erasure (core.services.gdpr.delete_user_data): deletes every
relational row AND the user's stored objects (uploaded face photos + generated
results in S3/MinIO), so a right-to-erasure request leaves no trace — not even
orphaned biometric images the DB rows used to point at."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import func, select

from core.db import SessionFactory, engine
from core.models import Base, GalleryItem, GenerationJob, User
from core.services import gdpr


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_erasure_deletes_user_storage_objects(monkeypatch):
    deleted: list[str] = []

    async def _fake_delete(url: str) -> bool:
        deleted.append(url)
        return True

    monkeypatch.setattr(gdpr_storage_target(), "delete", _fake_delete)

    async with SessionFactory() as s:
        s.add(User(user_id=1, language_code="ru", credits=0))
        s.add(GenerationJob(
            user_id=1, service="photoeffect", status="complete",
            result_url="https://cdn.example/results/out.mp4",
            params={"input_images": [
                "https://cdn.example/uploads/face1.jpg",
                {"url": "https://cdn.example/uploads/face2.jpg"},
            ]},
        ))
        s.add(GalleryItem(user_id=1, image_url="https://cdn.example/gallery/g1.png",
                          status="approved"))
        await s.commit()

    async with SessionFactory() as s:
        counts = await gdpr.delete_user_data(s, 1)
        await s.commit()

    # Every stored object the user's rows referenced was handed to storage.delete.
    assert set(deleted) == {
        "https://cdn.example/results/out.mp4",
        "https://cdn.example/uploads/face1.jpg",
        "https://cdn.example/uploads/face2.jpg",
        "https://cdn.example/gallery/g1.png",
    }
    assert counts["storage_objects_deleted"] == 4

    # And the relational trace is gone.
    async with SessionFactory() as s:
        assert await s.scalar(select(func.count()).select_from(User)) == 0
        assert await s.scalar(select(func.count()).select_from(GenerationJob)) == 0
        assert await s.scalar(select(func.count()).select_from(GalleryItem)) == 0


async def test_erasure_survives_storage_delete_failure(monkeypatch):
    """A storage backend hiccup must not abort the relational erasure (best-effort)."""
    async def _boom(url: str) -> bool:
        raise RuntimeError("s3 down")

    monkeypatch.setattr(gdpr_storage_target(), "delete", _boom)

    async with SessionFactory() as s:
        s.add(User(user_id=2, language_code="ru", credits=0))
        s.add(GenerationJob(user_id=2, service="photoeffect", status="complete",
                            result_url="https://cdn.example/results/x.mp4", params={}))
        await s.commit()

    async with SessionFactory() as s:
        counts = await gdpr.delete_user_data(s, 2)
        await s.commit()

    assert counts["users"] == 1  # user still erased despite storage failure
    async with SessionFactory() as s:
        assert await s.scalar(select(func.count()).select_from(User)) == 0


def gdpr_storage_target():
    """The storage module object gdpr.delete_user_data calls .delete() on."""
    from core.services import storage
    return storage
