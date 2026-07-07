"""Traffic-source attribution (ТЗ §7).

Covers first-touch storage semantics in get_or_create_user and the admin
/traffic/sources grouped-count endpoint coroutine. Calls the endpoint directly
against a real SQLite DB, mirroring tests/test_business_admin.
"""
from __future__ import annotations

import pytest_asyncio

from api.admin import traffic
from core.db import SessionFactory, engine
from core.models import AdminUser, Base
from core.services.admin_auth import hash_password
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _admin(session, role="admin") -> AdminUser:
    a = AdminUser(email="t@x.io", password_hash=hash_password("x"), role=role, is_active=True)
    session.add(a)
    await session.commit()
    return a


async def test_source_stored_on_creation():
    async with SessionFactory() as s:
        user, created = await get_or_create_user(s, 1, source="instagram")
        assert created is True
        assert user.source == "instagram"


async def test_source_not_overwritten_on_second_call():
    async with SessionFactory() as s:
        user, created = await get_or_create_user(s, 2, source="tiktok")
        assert created is True
        assert user.source == "tiktok"
        # second touch with a different source must NOT change the stored value
        again, created2 = await get_or_create_user(s, 2, source="youtube")
        assert created2 is False
        assert again.source == "tiktok"


async def test_source_truncated_to_column_length():
    async with SessionFactory() as s:
        long = "x" * 200
        user, _ = await get_or_create_user(s, 3, source=long)
        assert user.source == "x" * 64


async def test_traffic_sources_grouped_counts_with_direct_bucket():
    async with SessionFactory() as s:
        await get_or_create_user(s, 10, source="instagram")
        await get_or_create_user(s, 11, source="instagram")
        await get_or_create_user(s, 12, source="tiktok")
        # no source -> direct bucket
        await get_or_create_user(s, 13)
        await get_or_create_user(s, 14)

        admin = await _admin(s)
        out = await traffic.traffic_sources(days=None, admin=admin, session=s)

    counts = {row["source"]: row["users"] for row in out}
    assert counts == {"instagram": 2, "(direct)": 2, "tiktok": 1}
    # busiest-first ordering
    assert out[0]["users"] >= out[-1]["users"]


async def test_traffic_sources_days_filter_limits_recent():
    from datetime import UTC, datetime, timedelta

    async with SessionFactory() as s:
        await get_or_create_user(s, 20, source="recent")
        old, _ = await get_or_create_user(s, 21, source="ancient")
        # backdate the old signup well outside the window
        old.created_at = datetime.now(UTC) - timedelta(days=90)
        await s.commit()

        admin = await _admin(s)
        out = await traffic.traffic_sources(days=7, admin=admin, session=s)

    sources = {row["source"] for row in out}
    assert "recent" in sources
    assert "ancient" not in sources
