"""Admin analytics: funnel + retention + content (ТЗ §8).

Calls the endpoint coroutines directly against a seeded SQLite DB (same pattern as
tests/test_ai_routing_admin). A small, hand-built cohort lets us assert exact
funnel/retention/content numbers."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from api.admin import analytics
from core.db import SessionFactory, engine
from core.models import (
    AdminUser,
    Base,
    GenerationJob,
    Transaction,
    UsageLog,
    User,
)
from core.services.admin_auth import hash_password

NOW = datetime.now(UTC)


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _admin(session) -> AdminUser:
    a = AdminUser(email="a@x.io", password_hash=hash_password("x"),
                  role="admin", is_active=True)
    session.add(a)
    await session.commit()
    return a


async def _seed(session) -> None:
    """4 signup-cohort users (all created 40d ago):
      u1 — job + 2 paid tx + recent activity  → registered/activated/purchased/repeat, retained
      u2 — job + 1 paid tx + recent activity  → registered/activated/purchased, retained
      u3 — only an old job (at signup)         → registered/activated, NOT retained
      u4 — nothing                             → registered only, NOT retained
    """
    signup = NOW - timedelta(days=40)
    for uid in (1, 2, 3, 4):
        session.add(User(user_id=uid, username=f"u{uid}", created_at=signup))

    # generation jobs (drive funnel "activated" + content analytics)
    session.add(GenerationJob(user_id=1, service="video", model_variant="veo",
                              created_at=NOW - timedelta(days=35)))
    session.add(GenerationJob(user_id=2, service="photo", model_variant="mj",
                              created_at=NOW - timedelta(days=35)))
    session.add(GenerationJob(user_id=3, service="video", model_variant="veo",
                              created_at=signup))  # only activity → not retained

    # paid transactions (funnel purchased/repeat)
    for _ in range(2):
        session.add(Transaction(user_id=1, product="premium", amount=100,
                                gateway="stars", status="paid"))
    session.add(Transaction(user_id=2, product="premium", amount=100,
                            gateway="stars", status="paid"))

    # recent activity makes u1 & u2 retained (last activity = now >= signup + k)
    session.add(UsageLog(user_id=1, action="chat", created_at=NOW))
    session.add(UsageLog(user_id=2, action="chat", created_at=NOW))
    await session.commit()


async def test_funnel_stage_counts():
    async with SessionFactory() as s:
        admin = await _admin(s)
        await _seed(s)
        out = await analytics.funnel(days=60, admin=admin, session=s)
        counts = {st["stage"]: st["count"] for st in out["stages"]}
        assert counts == {"registered": 4, "activated": 3, "purchased": 2, "repeat": 1}
        # stages are monotonically non-increasing
        vals = [st["count"] for st in out["stages"]]
        assert vals == sorted(vals, reverse=True)


async def test_funnel_monotonic_when_users_pay_without_generating():
    """A user can PURCHASE without ever running a generation (buys Premium and churns
    — a top-up/subscription creates NO GenerationJob). The funnel must stay
    monotonically non-increasing (purchased ⊆ activated): a payer is, by definition,
    past activation. Regression for the widening-funnel bug — fails on the old logic
    where activated only counted job_exists (activated 0 < purchased 2)."""
    async with SessionFactory() as s:
        admin = await _admin(s)
        signup = NOW - timedelta(days=10)
        for uid in (101, 102):
            s.add(User(user_id=uid, username=f"buyer{uid}", created_at=signup))
            s.add(Transaction(user_id=uid, product="premium", amount=100,
                              gateway="stars", status="paid"))
        await s.commit()

        out = await analytics.funnel(days=30, admin=admin, session=s)
        c = {st["stage"]: st["count"] for st in out["stages"]}
        assert c["registered"] == 2
        assert c["purchased"] == 2
        assert c["activated"] == 2          # both buyers count as activated-or-beyond
        assert c["activated"] >= c["purchased"]  # the funnel must NOT widen
        vals = [st["count"] for st in out["stages"]]
        assert vals == sorted(vals, reverse=True)


async def test_content_top_services_and_models():
    async with SessionFactory() as s:
        admin = await _admin(s)
        await _seed(s)
        out = await analytics.content(days=60, admin=admin, session=s)
        svc = {r["name"]: r["count"] for r in out["top_services"]}
        mdl = {r["name"]: r["count"] for r in out["top_models"]}
        assert svc == {"video": 2, "photo": 1}
        assert mdl == {"veo": 2, "mj": 1}
        # most-used first
        assert out["top_services"][0]["name"] == "video"


async def test_retention_rolling_buckets():
    async with SessionFactory() as s:
        admin = await _admin(s)
        await _seed(s)
        out = await analytics.retention(days=60, admin=admin, session=s)
        # all 4 signed up 40d ago → eligible for every bucket
        assert out["eligible_d1"] == out["eligible_d7"] == out["eligible_d30"] == 4
        # u1 & u2 active "now" (>= signup + k) → retained; u3 (old) & u4 (none) not
        assert out["d7"] == 50.0
        assert out["d30"] == 50.0
