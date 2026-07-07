"""Reworked «Платежи» page — enriched + paginated transaction list and the accurate
windowed aggregates behind it (no migration):

  * GET /payments        — now returns {items, total, limit, offset, has_more} with
    an enriched per-row view and indexed filters (status/gateway/user_id/since/until)
    + pagination.
  * GET /payments/stats  — currency-aware aggregates over the WHOLE window
    (by_status / by_gateway / revenue_by_currency / revenue_by_day / paid_users).

Calls the endpoint coroutines directly against a seeded SQLite DB, mirroring
tests/test_refunds_admin.py.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from api.admin import ops
from core.db import SessionFactory, engine
from core.models import AdminUser, Base, Transaction, User


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


class _Admin:
    id = 1


async def _admin(session) -> AdminUser:
    a = AdminUser(email="ops@x.io", password_hash="x", role="admin", is_active=True)
    session.add(a)
    await session.commit()
    return a


async def _seed():
    async with SessionFactory() as s:
        s.add(User(user_id=1))
        s.add(User(user_id=2))
        now = datetime.now(UTC)
        # gateway=stars: 2 paid (100+100 stars), 1 failed
        s.add(Transaction(user_id=1, product="credits", qty=100, amount=100,
                          currency="stars", gateway="stars", status="paid",
                          credits_added=100, created_at=now))
        s.add(Transaction(user_id=2, product="credits", qty=100, amount=100,
                          currency="stars", gateway="stars", status="paid",
                          created_at=now))
        s.add(Transaction(user_id=1, product="credits", amount=50, currency="stars",
                          gateway="stars", status="failed", created_at=now))
        # gateway=yookassa: 1 paid (1200 rub), with full enrichment fields
        s.add(Transaction(user_id=1, product="premium", duration_months=2, amount=1200,
                          currency="rub", gateway="yookassa", gateway_tx_id="yk_1",
                          status="paid", paid_at=now, created_at=now))
        await s.commit()


# ---- enriched + paginated list ---------------------------------------------
async def test_list_returns_paged_envelope_with_enriched_rows():
    await _seed()
    async with SessionFactory() as s:
        out = await ops.list_payments(admin=_Admin(), session=s)
    assert out["total"] == 4
    assert out["has_more"] is False
    assert len(out["items"]) == 4
    # premium row carries the enriched columns (no migration).
    prem = next(i for i in out["items"] if i["product"] == "premium")
    assert prem["duration_months"] == 2
    assert prem["gateway_tx_id"] == "yk_1"
    assert prem["paid_at"] is not None
    assert prem["currency"] == "rub"


async def test_list_filters_and_pagination():
    await _seed()
    async with SessionFactory() as s:
        # filter by gateway
        out = await ops.list_payments(gateway="stars", admin=_Admin(), session=s)
        assert out["total"] == 3
        # filter by user_id
        u2 = await ops.list_payments(user_id=2, admin=_Admin(), session=s)
        assert u2["total"] == 1 and u2["items"][0]["user_id"] == 2
        # status filter
        paid = await ops.list_payments(status="paid", admin=_Admin(), session=s)
        assert paid["total"] == 3
        # pagination: limit 2 → has_more, offset advances
        page1 = await ops.list_payments(limit=2, offset=0, admin=_Admin(), session=s)
        assert len(page1["items"]) == 2 and page1["has_more"] is True
        page2 = await ops.list_payments(limit=2, offset=2, admin=_Admin(), session=s)
        assert len(page2["items"]) == 2 and page2["has_more"] is False


async def test_list_since_filter_excludes_old():
    await _seed()
    async with SessionFactory() as s:
        # add an old paid tx well before the window
        old = datetime.now(UTC) - timedelta(days=400)
        s.add(Transaction(user_id=1, product="credits", amount=10, currency="stars",
                          gateway="stars", status="paid", created_at=old))
        await s.commit()
    cutoff = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    async with SessionFactory() as s:
        out = await ops.list_payments(since=cutoff, admin=_Admin(), session=s)
    # the 400-day-old row is excluded; the 4 fresh ones remain.
    assert out["total"] == 4


# ---- windowed stats --------------------------------------------------------
async def test_stats_currency_aware_aggregates():
    await _seed()
    async with SessionFactory() as s:
        out = await ops.payments_stats(days=30, admin=_Admin(), session=s)

    assert out["totals"]["count"] == 4
    assert out["totals"]["paid"] == 3
    assert out["totals"]["failed"] == 1
    # revenue never cross-summed — broken down per currency.
    assert out["revenue_by_currency"]["stars"] == 200
    assert out["revenue_by_currency"]["rub"] == 1200
    # per-gateway accuracy over the whole window (not just a page).
    by_gw = {g["gateway"]: g for g in out["by_gateway"]}
    assert by_gw["stars"]["count"] == 3
    assert by_gw["stars"]["paid"] == 2
    assert by_gw["stars"]["success_pct"] == round(2 / 3 * 100, 1)
    assert by_gw["stars"]["revenue_by_currency"]["stars"] == 200
    assert by_gw["yookassa"]["paid"] == 1
    assert by_gw["yookassa"]["revenue_by_currency"]["rub"] == 1200
    # distinct paid users (user 1 + user 2).
    assert out["paid_users"] == 2
    # daily series present and paid-only.
    assert sum(d["count"] for d in out["revenue_by_day"]) == 3


async def test_stats_empty_window():
    async with SessionFactory() as s:
        out = await ops.payments_stats(days=7, admin=_Admin(), session=s)
    assert out["totals"]["count"] == 0
    assert out["by_gateway"] == []
    assert out["revenue_by_currency"] == {}
    assert out["paid_users"] == 0
