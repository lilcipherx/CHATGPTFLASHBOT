"""Broadcast admin endpoints — enriched list + cancel state machine.

Calls the endpoint coroutines directly against a seeded SQLite schema (no HTTP),
mirroring the project's other direct-call admin tests. Covers the two backend
additions behind the reworked Broadcasts control center:
  * GET /broadcasts now returns content / scheduled_at / admin_id / resolved author.
  * POST /broadcasts/{id}/cancel only cancels a 'scheduled' broadcast (409 else).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException

from api.admin.ops import (
    BroadcastRequest,
    EstimateRequest,
    cancel_broadcast,
    create_broadcast,
    estimate_broadcast,
    list_broadcasts,
)
from core.db import SessionFactory, engine
from core.models import AdminUser, Base, Broadcast, User


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


_REQ = SimpleNamespace(client=None)  # _ip() returns "" when client is None


async def _seed_admin() -> AdminUser:
    async with SessionFactory() as s:
        admin = AdminUser(email="ops@example.com", password_hash="x", role="admin")
        s.add(admin)
        await s.commit()
        await s.refresh(admin)
        return admin


async def test_list_returns_enriched_fields():
    admin = await _seed_admin()
    when = datetime.now(UTC) + timedelta(hours=2)
    async with SessionFactory() as s:
        s.add(Broadcast(
            admin_id=admin.id, segment={"tier": "premium", "language": "ru"},
            content={"title": "Summer", "text": "<b>Hi</b>"},
            scheduled_at=when, status="scheduled", sent=0, failed=0,
        ))
        await s.commit()

    async with SessionFactory() as s:
        rows = await list_broadcasts(admin=admin, session=s)

    assert len(rows) == 1
    row = rows[0]
    assert row["content"]["title"] == "Summer"
    assert row["segment"] == {"tier": "premium", "language": "ru"}
    assert row["scheduled_at"] is not None
    assert row["admin_id"] == admin.id
    assert row["author"] == "ops@example.com"  # resolved from AdminUser.email


async def test_cancel_scheduled_flips_to_cancelled():
    admin = await _seed_admin()
    async with SessionFactory() as s:
        bc = Broadcast(admin_id=admin.id, segment={}, content={}, status="scheduled")
        s.add(bc)
        await s.commit()
        bc_id = bc.id

    async with SessionFactory() as s:
        res = await cancel_broadcast(bc_id, request=_REQ, admin=admin, session=s)
    assert res["status"] == "cancelled"

    async with SessionFactory() as s:
        bc = await s.get(Broadcast, bc_id)
        assert bc.status == "cancelled"


async def test_cancel_rejects_non_scheduled():
    admin = await _seed_admin()
    async with SessionFactory() as s:
        bc = Broadcast(admin_id=admin.id, segment={}, content={}, status="sending")
        s.add(bc)
        await s.commit()
        bc_id = bc.id

    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await cancel_broadcast(bc_id, request=_REQ, admin=admin, session=s)
    assert ei.value.status_code == 409


async def test_cancel_missing_returns_404():
    admin = await _seed_admin()
    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await cancel_broadcast(999, request=_REQ, admin=admin, session=s)
    assert ei.value.status_code == 404


async def test_estimate_counts_segment_excluding_banned():
    """The audience preview uses the same predicate as the worker: premium-only,
    banned always excluded."""
    admin = await _seed_admin()
    now = datetime.now(UTC)
    async with SessionFactory() as s:
        s.add_all([
            User(user_id=1, sub_tier="premium", sub_expires=now + timedelta(days=10)),
            User(user_id=2, sub_tier="premium", sub_expires=now + timedelta(days=10),
                 is_banned=True),
            User(user_id=3, sub_tier=None, sub_expires=None),
        ])
        await s.commit()

    async with SessionFactory() as s:
        all_out = await estimate_broadcast(EstimateRequest(segment={}), admin=admin, session=s)
        prem_out = await estimate_broadcast(
            EstimateRequest(segment={"tier": "premium"}), admin=admin, session=s)
    assert all_out["count"] == 2          # banned (2) excluded
    assert prem_out["count"] == 1         # only the active, non-banned premium


async def test_create_immediate_is_queued(monkeypatch):
    """An immediate send is born 'queued' (not 'scheduled') so the history never
    flashes a misleading badge before the worker picks it up."""
    admin = await _seed_admin()
    enqueued: list = []

    async def _fake_enqueue(fn, *args, **kw):
        enqueued.append((fn, args))

    monkeypatch.setattr("api.admin.ops.enqueue", _fake_enqueue)

    async with SessionFactory() as s:
        out = await create_broadcast(
            BroadcastRequest(segment={}, text="hi"), request=_REQ, admin=admin, session=s,
        )
    assert out["status"] == "queued"
    assert enqueued and enqueued[0][0] == "run_broadcast"
    async with SessionFactory() as s:
        bc = await s.get(Broadcast, out["id"])
        assert bc.status == "queued" and bc.scheduled_at is None


async def test_create_scheduled_stays_scheduled(monkeypatch):
    admin = await _seed_admin()
    enqueued: list = []

    async def _fake_enqueue(fn, *args, **kw):
        enqueued.append((fn, args))

    monkeypatch.setattr("api.admin.ops.enqueue", _fake_enqueue)
    when = (datetime.now(UTC) + timedelta(hours=3)).isoformat()

    async with SessionFactory() as s:
        out = await create_broadcast(
            BroadcastRequest(segment={}, text="later", scheduled_at=when),
            request=_REQ, admin=admin, session=s,
        )
    assert out["status"] == "scheduled"
    assert enqueued == []   # deferred sends are NOT enqueued now
    async with SessionFactory() as s:
        bc = await s.get(Broadcast, out["id"])
        assert bc.status == "scheduled" and bc.scheduled_at is not None
