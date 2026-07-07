"""Reworked «Аудит-лог» page — the enriched reader + dashboard aggregates behind the
Audit Center (no migration; before/after/ip already exist on admin_audit_log):

  * GET /audit       — now enriches each row with admin email/role + before/after
    snapshots and supports target_type/target_id/q/until/offset filters, ordered by
    the indexed PK.
  * GET /audit/stats — total/today/last-hour counters, category & verb buckets,
    by_day series, and top admins.

Calls the endpoint coroutines directly against a seeded SQLite DB.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from api.admin import ops
from core.db import SessionFactory, engine
from core.models import AdminAuditLog, AdminUser, Base


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


class _Admin:
    id = 1


async def _seed():
    async with SessionFactory() as s:
        s.add(AdminUser(id=10, email="root@x.io", password_hash="x", role="superadmin"))
        s.add(AdminUser(id=11, email="mod@x.io", password_hash="x", role="moderator"))
        now = datetime.now(UTC)
        # (admin_id, action, target_type, target_id, before, after, ip)
        rows = [
            (10, "banner.create", "banner", "12", None, {"title": "A"}, "1.1.1.1"),
            (10, "banner.update", "banner", "12", {"title": "A"}, {"title": "B"}, "1.1.1.1"),
            (11, "banner.delete", "banner", "12", {"title": "B"}, None, "2.2.2.2"),
            (10, "payment.refund", "transaction", "tx1", None, {"status": "ok"}, "1.1.1.1"),
            (11, "admin.role", "admin", "11", {"role": "support"}, {"role": "mod"}, "2.2.2.2"),
        ]
        for aid, act, tt, tid, bf, af, ip in rows:
            s.add(AdminAuditLog(admin_id=aid, action=act, target_type=tt, target_id=tid,
                                before=bf, after=af, ip=ip, created_at=now))
        await s.commit()


# ---- enriched list ---------------------------------------------------------
async def test_list_enriched_with_admin_and_snapshots():
    await _seed()
    out = None
    async with SessionFactory() as s:
        out = await ops.list_audit(admin=_Admin(), session=s)
    assert len(out) == 5
    # newest first by PK (the admin.role row was inserted last).
    assert out[0]["action"] == "admin.role"
    upd = next(r for r in out if r["action"] == "banner.update")
    assert upd["admin_email"] == "root@x.io"
    assert upd["admin_role"] == "superadmin"
    assert upd["before"] == {"title": "A"}
    assert upd["after"] == {"title": "B"}


async def test_list_filters_target_and_q_and_offset():
    await _seed()
    async with SessionFactory() as s:
        # object history: everything on banner:12
        hist = await ops.list_audit(target_type="banner", target_id="12", admin=_Admin(), session=s)
        assert len(hist) == 3
        assert [r["action"] for r in hist] == ["banner.delete", "banner.update", "banner.create"]
        # free-text q matches an IP
        by_ip = await ops.list_audit(q="2.2.2.2", admin=_Admin(), session=s)
        assert len(by_ip) == 2
        # action substring
        pay = await ops.list_audit(action="payment", admin=_Admin(), session=s)
        assert len(pay) == 1 and pay[0]["target_id"] == "tx1"
        # pagination: limit + offset
        page1 = await ops.list_audit(limit=2, offset=0, admin=_Admin(), session=s)
        page2 = await ops.list_audit(limit=2, offset=2, admin=_Admin(), session=s)
        assert len(page1) == 2 and len(page2) == 2
        assert page1[0]["id"] != page2[0]["id"]


async def test_list_until_excludes_recent():
    await _seed()
    async with SessionFactory() as s:
        old = datetime.now(UTC) - timedelta(days=400)
        s.add(AdminAuditLog(admin_id=10, action="old.event", created_at=old))
        await s.commit()
    cutoff = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    async with SessionFactory() as s:
        out = await ops.list_audit(until=cutoff, admin=_Admin(), session=s)
    assert len(out) == 1 and out[0]["action"] == "old.event"


# ---- stats -----------------------------------------------------------------
async def test_stats_buckets_and_categories():
    await _seed()
    async with SessionFactory() as s:
        out = await ops.audit_stats(days=30, admin=_Admin(), session=s)

    assert out["total"] == 5
    assert out["today"] == 5
    assert out["last_hour"] == 5
    assert out["admins_total"] == 2
    assert out["distinct_admins"] == 2
    assert out["last_action_at"] is not None

    # verb buckets: 1 create, 1 update, 1 delete, refund→delete bucket, admin.role→security
    b = out["buckets"]
    assert b["create"] == 1            # banner.create
    assert b["delete"] == 2            # banner.delete + payment.refund (destructive)
    assert b["security"] == 1          # admin.role (admin. prefix)
    assert b["update"] == 1            # banner.update

    cats = {c["category"]: c["count"] for c in out["by_category"]}
    assert cats["banner"] == 3
    assert cats["payment"] == 1
    assert cats["admin"] == 1

    top = {t["admin_id"]: t["count"] for t in out["top_admins"]}
    assert top[10] == 3 and top[11] == 2
    assert any(d["count"] > 0 for d in out["by_day"])


async def test_stats_empty():
    async with SessionFactory() as s:
        out = await ops.audit_stats(days=7, admin=_Admin(), session=s)
    assert out["total"] == 0
    assert out["buckets"]["delete"] == 0
    assert out["by_category"] == []
    assert out["top_admins"] == []
