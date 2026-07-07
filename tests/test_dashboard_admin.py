"""Admin dashboard aggregation endpoint (api/admin/ops.dashboard) — ТЗ §8.

test_admin.py only asserts the route is mounted; this proves every KPI's actual
computation (counts, SUM, GROUP BY gateway/status) against a real SQLite DB by
calling the endpoint coroutine directly, mirroring tests/test_attention.py.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest_asyncio

from api.admin import ops
from core.db import SessionFactory, engine
from core.models import AdminUser, Base, GenerationJob, Transaction, User
from core.redis_client import redis_client
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    # The endpoint short-circuits on a cached payload; clear every period's key so
    # each test computes fresh from the DB it just seeded (fakeredis persists across
    # tests in-process). The payload is cached per-period as "<key>:<period>".
    try:
        for p in ops._PERIODS:
            await redis_client.delete(f"{ops._DASHBOARD_CACHE_KEY}:{p}")
    except Exception:  # noqa: BLE001
        pass
    yield
    await engine.dispose()


async def _admin(session, role="support") -> AdminUser:
    a = AdminUser(email="a@x.io", password_hash=hash_password("x"), role=role, is_active=True)
    session.add(a)
    await session.commit()
    return a


async def test_empty_db_zeros():
    async with SessionFactory() as s:
        a = await _admin(s)
        out = await ops.dashboard(admin=a, session=s)
    assert out["total_users"] == 0
    assert out["active_subscriptions"] == 0
    assert out["paid_transactions"] == 0
    assert out["credits_total"] == 0
    assert out["revenue_by_gateway"] == {}
    assert out["revenue_by_currency"] == {}
    assert out["jobs_by_status"] == {}
    assert out["completed_generations"] == 0
    assert out["pending_jobs"] == 0
    assert out["conversion_pct"] == 0.0
    assert out["dau"] == 0 and out["mau"] == 0


async def test_kpis_computed_from_db():
    now = datetime.now(UTC)
    async with SessionFactory() as s:
        a = await _admin(s)
        # 3 users: one recent + premium-active, one banned, one plain.
        s.add(User(user_id=1, created_at=now, sub_expires=now + timedelta(days=10),
                   sub_tier="premium", credits=100))
        s.add(User(user_id=2, created_at=now - timedelta(days=30), is_banned=True, credits=50))
        s.add(User(user_id=3, created_at=now, credits=25))
        # paid transactions across two gateways (+ one pending that must not count).
        s.add(Transaction(user_id=1, product="premium", amount=500, currency="rub",
                          gateway="yookassa", status="paid"))
        s.add(Transaction(user_id=1, product="credits", amount=300, currency="stars",
                          gateway="stars", status="paid"))
        s.add(Transaction(user_id=3, product="credits", amount=999, currency="rub",
                          gateway="yookassa", status="pending"))
        # generation jobs in several statuses.
        for st in ("complete", "complete", "processing", "pending", "failed"):
            s.add(GenerationJob(job_id=uuid.uuid4(), user_id=1, service="image", status=st))
        await s.commit()

        out = await ops.dashboard(admin=a, session=s)

    assert out["total_users"] == 3
    assert out["new_users_7d"] == 2          # users 1 & 3 created within 7 days
    assert out["active_subscriptions"] == 1  # only user 1 (sub_expires in the future)
    assert out["banned_users"] == 1
    assert out["credits_total"] == 175       # 100 + 50 + 25
    assert out["paid_transactions"] == 2     # the pending tx excluded
    assert out["revenue_by_gateway"] == {"yookassa": 500, "stars": 300}  # paid only
    assert out["jobs_by_status"] == {"complete": 2, "processing": 1, "pending": 1, "failed": 1}
    assert out["completed_generations"] == 2
    assert out["pending_jobs"] == 2          # pending + processing
    # revenue is split by currency (never summed across them) and by gateway within
    assert out["revenue_by_currency"]["rub"] == {
        "total": 500, "count": 1, "avg_check": 500, "by_gateway": {"yookassa": 500},
    }
    assert out["revenue_by_currency"]["stars"] == {
        "total": 300, "count": 1, "avg_check": 300, "by_gateway": {"stars": 300},
    }
    # conversion: 1 of 3 users paid → 33.33%; only user 1 has paid transactions
    assert out["paying_users"] == 1
    assert out["conversion_pct"] == 33.33
    # engagement: all 3 rows were just written, so they count as active in every window
    assert out["mau"] == 3
    assert out["dau"] == 3
