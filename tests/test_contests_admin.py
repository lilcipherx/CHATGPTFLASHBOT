"""Admin contest endpoints: entrants list, winners-from-audit, and edit.

Calls the endpoint coroutines directly against a seeded SQLite schema.
"""
from __future__ import annotations

import types

import pytest
import pytest_asyncio
from fastapi import HTTPException

from api.admin import contests as admin_contests
from core.db import SessionFactory, engine
from core.models import AdminAuditLog, AdminUser, Base
from core.services import contests
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req():
    return types.SimpleNamespace(client=types.SimpleNamespace(host="10.0.0.1"))


async def _admin(s) -> AdminUser:
    a = AdminUser(email="a@x.io", password_hash=hash_password("x"), role="admin", is_active=True)
    s.add(a)
    await s.commit()
    await s.refresh(a)
    return a


async def test_entrants_lists_users():
    async with SessionFactory() as s:
        admin = await _admin(s)
        c = await contests.create(s, "Giveaway", None, 1)
        await contests.enter(s, c.id, 101)
        await contests.enter(s, c.id, 102)
        out = await admin_contests.contest_entrants(c.id, admin=admin, session=s)
    assert {e["user_id"] for e in out["entrants"]} == {101, 102}
    assert all(e["entered_at"] for e in out["entrants"])


async def test_winners_recovered_from_draw_audit():
    """Winners aren't stored on the contest; the endpoint recovers them from the most
    recent contest.draw audit row."""
    async with SessionFactory() as s:
        admin = await _admin(s)
        c = await contests.create(s, "Prize", None, 2)
        s.add(AdminAuditLog(admin_id=admin.id, action="contest.draw",
                            target_type="contest", target_id=str(c.id),
                            after={"winners": [777, 888]}))
        await s.commit()
        out = await admin_contests.contest_winners(c.id, admin=admin, session=s)
    assert out["winners"] == [777, 888]
    assert out["drawn_at"] is not None


async def test_winners_empty_when_never_drawn():
    async with SessionFactory() as s:
        admin = await _admin(s)
        c = await contests.create(s, "Untouched", None, 1)
        out = await admin_contests.contest_winners(c.id, admin=admin, session=s)
    assert out["winners"] == []


async def test_update_contest_edits_terms():
    async with SessionFactory() as s:
        admin = await _admin(s)
        c = await contests.create(s, "Old", "old desc", 1)
        out = await admin_contests.update_contest(
            c.id,
            admin_contests.UpdateContest(title="New", description="new desc", winners_count=3),
            _req(), admin=admin, session=s,
        )
        assert out["title"] == "New" and out["winners_count"] == 3
        assert out["description"] == "new desc"


async def test_update_rejected_after_draw():
    async with SessionFactory() as s:
        admin = await _admin(s)
        admin_id = admin.id
        c = await contests.create(s, "Drawn", None, 1)
        await contests.enter(s, c.id, 1)
        await contests.draw(s, c.id)   # flips status to drawn
        cid = c.id
    # Fresh session (like a real separate request) so the drawn status is read clean.
    async with SessionFactory() as s:
        admin = await s.get(AdminUser, admin_id)
        with pytest.raises(HTTPException) as ei:
            await admin_contests.update_contest(
                cid, admin_contests.UpdateContest(title="X", winners_count=1),
                _req(), admin=admin, session=s,
            )
        assert ei.value.status_code == 400
