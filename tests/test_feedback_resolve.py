"""Complaint resolution (ТЗ §7 admin feedback): resolve clears it from the open list."""
from __future__ import annotations

import types

import pytest_asyncio

from api.admin import feedback as feedback_api
from core.db import SessionFactory, engine
from core.models import AdminUser, Base
from core.services import feedback
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req():
    return types.SimpleNamespace(client=None)


async def _admin(session) -> AdminUser:
    a = AdminUser(email="f@x.io", password_hash=hash_password("x"), role="admin", is_active=True)
    session.add(a)
    await session.commit()
    return a


async def test_resolve_clears_from_open_list():
    async with SessionFactory() as s:
        admin = await _admin(s)
        c = await feedback.record_complaint(s, user_id=10, content="плохо")
        assert (await feedback.stats(s))["complaints_open"] == 1

        out = await feedback_api.resolve_complaint(c.id, _req(), admin=admin, session=s)
        assert out["ok"] is True
        assert (await feedback.stats(s))["complaints_open"] == 0
        open_rows = await feedback_api.open_complaints(admin=admin, session=s)
        assert open_rows == []


async def test_resolve_unknown_404():
    import pytest
    async with SessionFactory() as s:
        admin = await _admin(s)
        with pytest.raises(Exception):  # noqa: B017,PT011 — HTTPException(404)
            await feedback_api.resolve_complaint(999, _req(), admin=admin, session=s)


async def test_open_complaints_paginates_and_bounds():
    async with SessionFactory() as s:
        admin = await _admin(s)
        for i in range(5):
            await feedback.record_complaint(s, user_id=100 + i, content=f"c{i}")

        # Default call returns all 5 (under the cap), newest first.
        all_rows = await feedback_api.open_complaints(admin=admin, session=s)
        assert len(all_rows) == 5

        # limit + offset page through the queue without overlap.
        page1 = await feedback_api.open_complaints(limit=2, offset=0, admin=admin, session=s)
        page2 = await feedback_api.open_complaints(limit=2, offset=2, admin=admin, session=s)
        assert len(page1) == 2 and len(page2) == 2
        assert {r["id"] for r in page1}.isdisjoint({r["id"] for r in page2})

        # An over-large / non-positive limit is clamped (never unbounded, never empty).
        capped = await feedback_api.open_complaints(limit=99999, offset=0, admin=admin, session=s)
        assert len(capped) == 5
