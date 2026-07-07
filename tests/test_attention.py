"""Admin «Требует внимания» endpoint (api/admin/attention) — ТЗ §8.

Calls the endpoint coroutine directly against a real SQLite DB, mirroring
tests/test_business_admin.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest_asyncio

from api.admin import attention
from core.config import settings
from core.db import SessionFactory, engine
from core.models import (
    AdminUser,
    Base,
    ChannelPost,
    Complaint,
    GalleryItem,
    GenerationJob,
    SupportMessage,
)
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    # The file-based SQLite engine pools connections that pytest-asyncio's per-test
    # event loop leaves bound after this test; dispose so the next test's create_all
    # and session share a clean loop binding (avoids sporadic "no such table").
    await engine.dispose()


async def _admin(session, role="admin") -> AdminUser:
    a = AdminUser(email="a@x.io", password_hash=hash_password("x"), role=role, is_active=True)
    session.add(a)
    await session.commit()
    return a


async def test_empty_db_all_zeros():
    async with SessionFactory() as s:
        a = await _admin(s)
        out = await attention.attention(admin=a, session=s)
    assert out == {
        "stuck_jobs": 0,
        "open_complaints": 0,
        "pending_gallery": 0,
        "open_support": 0,
        "failed_channel_posts": 0,
        "total": 0,
    }


async def test_counts_each_category():
    old = datetime.now(UTC) - timedelta(minutes=settings.stuck_job_minutes + 10)
    async with SessionFactory() as s:
        a = await _admin(s)

        # A stuck job: pending, created before the threshold.
        s.add(GenerationJob(
            job_id=uuid.uuid4(), user_id=1, service="image",
            status="pending", created_at=old,
        ))
        # A fresh pending job that must NOT count as stuck.
        s.add(GenerationJob(
            job_id=uuid.uuid4(), user_id=1, service="image",
            status="pending", created_at=datetime.now(UTC),
        ))
        # An unresolved complaint (+ one resolved that must not count).
        s.add(Complaint(user_id=1, content="bad", resolved=False))
        s.add(Complaint(user_id=1, content="ok now", resolved=True))
        # A pending gallery item (+ an approved one that must not count).
        s.add(GalleryItem(user_id=1, image_url="http://x/a.png", status="pending"))
        s.add(GalleryItem(user_id=1, image_url="http://x/b.png", status="approved"))
        # An unhandled inbound support message (+ a handled one + an outbound one).
        s.add(SupportMessage(user_id=1, direction="in", text="help", handled=False))
        s.add(SupportMessage(user_id=1, direction="in", text="done", handled=True))
        s.add(SupportMessage(user_id=1, direction="out", text="reply", admin_id=a.id))
        # A failed channel post (+ a sent one that must not count).
        s.add(ChannelPost(channel="@c", text="x", status="failed"))
        s.add(ChannelPost(channel="@c", text="y", status="sent"))
        await s.commit()

        out = await attention.attention(admin=a, session=s)

    assert out["stuck_jobs"] == 1
    assert out["open_complaints"] == 1
    assert out["pending_gallery"] == 1
    assert out["open_support"] == 1
    assert out["failed_channel_posts"] == 1
    assert out["total"] == 5
