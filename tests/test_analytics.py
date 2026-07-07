"""Admin analytics endpoints (api/admin/analytics) — ТЗ §8.

Calls the endpoint coroutines directly against a real SQLite DB, mirroring
tests/test_business_admin & tests/test_exports.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest_asyncio

from api.admin import analytics
from core.db import SessionFactory, engine
from core.models import AdminUser, Base, GenerationJob, Transaction, UsageLog, User
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _admin(session, role="admin") -> AdminUser:
    a = AdminUser(email="a@x.io", password_hash=hash_password("x"), role=role, is_active=True)
    session.add(a)
    await session.commit()
    return a


def _tx(user_id: int, amount: int, status: str, when: datetime, currency="rub"):
    return Transaction(
        tx_id=uuid.uuid4(), user_id=user_id, product="premium", amount=amount,
        currency=currency, gateway="yookassa", status=status, created_at=when,
    )


async def test_summary_revenue_paid_only_and_conversion():
    now = datetime.now(UTC)
    day1 = now - timedelta(days=2)
    day2 = now - timedelta(days=1)
    async with SessionFactory() as s:
        a = await _admin(s)
        # 4 users total, 2 of whom pay → conversion 50%
        s.add_all([
            User(user_id=1, username="u1", created_at=day1),
            User(user_id=2, username="u2", created_at=day2),
            User(user_id=3, username="u3", created_at=day2),
            User(user_id=4, username="u4", created_at=now),
        ])
        # paid: 500 (day1) + 300 (day2) + 200 (day2, same user 1) = 1000
        s.add(_tx(1, 500, "paid", day1))
        s.add(_tx(1, 200, "paid", day2))
        s.add(_tx(2, 300, "paid", day2))
        # pending must be excluded from revenue + paid_users
        s.add(_tx(3, 999, "pending", day2))
        await s.commit()

        out = await analytics.summary(days=30, admin=a, session=s)

    assert out["revenue_total"] == 1000          # paid only, pending 999 excluded
    assert out["paid_users"] == 2                 # users 1 and 2; user 3 only pending
    assert out["total_users"] == 4
    assert out["conversion_pct"] == 50.0          # 2/4 * 100
    assert out["arppu"] == 500.0                  # 1000 / 2
    assert out["arpu"] == 250.0                   # 1000 / 4
    assert out["revenue_by_currency"] == {"rub": 1000}
    # per-currency breakdown carries honest, non-cross-currency ARPU/ARPPU
    assert out["currencies"]["rub"] == {
        "revenue": 1000, "paid_users": 2, "arpu": 250.0, "arppu": 500.0,
    }

    # non-empty per-day revenue, summing to the total, pending excluded
    rev_days = out["revenue_by_day"]
    assert rev_days, "expected non-empty revenue_by_day"
    assert sum(r["amount"] for r in rev_days) == 1000
    assert 999 not in [r["amount"] for r in rev_days]

    # new-user trend present
    assert sum(r["count"] for r in out["new_users_by_day"]) == 4


async def test_summary_custom_range_is_closed_on_both_ends():
    """A custom since/until range includes both boundary days and EXCLUDES
    transactions outside it (older than since OR newer than until)."""
    now = datetime.now(UTC)
    async with SessionFactory() as s:
        a = await _admin(s)
        s.add(User(user_id=1, created_at=now - timedelta(days=20)))
        # inside the range (10 days ago) — counted
        s.add(_tx(1, 500, "paid", now - timedelta(days=10)))
        # before the range (25 days ago) — excluded
        s.add(_tx(1, 700, "paid", now - timedelta(days=25)))
        # after the range (today) — excluded
        s.add(_tx(1, 900, "paid", now))
        await s.commit()

        since = (now - timedelta(days=15)).date().isoformat()
        until = (now - timedelta(days=5)).date().isoformat()
        out = await analytics.summary(days=30, since=since, until=until, admin=a, session=s)

    assert out["start"] == since and out["end"] == until
    assert out["days"] == 11                      # 15..5 days ago inclusive
    assert out["revenue_total"] == 500            # only the in-range tx
    assert out["revenue_by_currency"] == {"rub": 500}


async def test_summary_empty_window_is_safe():
    async with SessionFactory() as s:
        a = await _admin(s)
        out = await analytics.summary(days=14, admin=a, session=s)
    assert out["revenue_total"] == 0
    assert out["paid_users"] == 0
    assert out["total_users"] == 0
    assert out["conversion_pct"] == 0.0
    assert out["arpu"] == 0.0 and out["arppu"] == 0.0
    assert out["revenue_by_day"] == []


async def test_geo_top_languages_and_countries():
    now = datetime.now(UTC)
    async with SessionFactory() as s:
        a = await _admin(s)
        s.add_all([
            User(user_id=1, language_code="ru", country="RU", created_at=now),
            User(user_id=2, language_code="ru", country="RU", created_at=now),
            User(user_id=3, language_code="en", country=None, created_at=now),
        ])
        await s.commit()
        out = await analytics.geo(days=30, admin=a, session=s)
    assert out["top_languages"] == [{"code": "ru", "count": 2}, {"code": "en", "count": 1}]
    # country only where set (user 3 has none) — sparse by design.
    assert out["top_countries"] == [{"code": "RU", "count": 2}]


async def test_dau_proxy_counts_distinct_users_per_day():
    now = datetime.now(UTC)
    async with SessionFactory() as s:
        a = await _admin(s)
        s.add_all([User(user_id=1), User(user_id=2)])
        # user 1 active via usage log + a job the same day → counted once
        s.add(UsageLog(user_id=1, action="chat", created_at=now))
        s.add(GenerationJob(user_id=1, service="suno", status="complete", created_at=now))
        # user 2 active via a paid transaction the same day
        s.add(_tx(2, 100, "paid", now))
        await s.commit()

        out = await analytics.dau(days=14, admin=a, session=s)

    assert out["dau_by_day"], "expected at least one DAU day"
    today = max(out["dau_by_day"], key=lambda r: r["date"])
    assert today["count"] == 2        # distinct users, user 1 not double-counted
