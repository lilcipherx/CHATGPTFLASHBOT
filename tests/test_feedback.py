"""Feedback service + admin endpoint (ТЗ §7): ratings, complaints, stats.

Direct-call pattern (no HTTP), same as test_business_admin / test_promo_bonuses.
"""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import select

from api.admin import feedback as admin_feedback
from core.db import SessionFactory, engine
from core.models import Base
from core.models.feedback import Complaint  # noqa: F401 — register table on metadata
from core.services import feedback


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_record_ratings_and_stats():
    async with SessionFactory() as s:
        await feedback.record_rating(s, 1, "up", "a great reply")
        await feedback.record_rating(s, 2, "up", None)
        await feedback.record_rating(s, 3, "down", "bad reply")
    async with SessionFactory() as s:
        out = await feedback.stats(s)
        assert out == {"up": 2, "down": 1, "complaints_open": 0}


async def test_snippet_is_trimmed():
    async with SessionFactory() as s:
        fb = await feedback.record_rating(s, 1, "up", "x" * 500)
        assert fb.snippet is not None and len(fb.snippet) == 200


async def test_record_complaint_appears_in_open_query():
    async with SessionFactory() as s:
        await feedback.record_complaint(s, 42, "the bot is broken")
    async with SessionFactory() as s:
        rows = (
            await s.scalars(select(Complaint).where(Complaint.resolved.is_(False)))
        ).all()
        assert len(rows) == 1
        assert rows[0].user_id == 42
        assert rows[0].content == "the bot is broken"
        assert rows[0].resolved is False
    async with SessionFactory() as s:
        out = await feedback.stats(s)
        assert out["complaints_open"] == 1


async def test_admin_stats_endpoint_shape():
    async with SessionFactory() as s:
        await feedback.record_rating(s, 1, "down", "meh")
        await feedback.record_complaint(s, 1, "complaint")
    async with SessionFactory() as s:
        out = await admin_feedback.feedback_stats(admin=None, session=s)
        assert out == {"up": 0, "down": 1, "complaints_open": 1}


async def test_admin_complaints_endpoint():
    async with SessionFactory() as s:
        await feedback.record_complaint(s, 7, "first")
    async with SessionFactory() as s:
        out = await admin_feedback.open_complaints(admin=None, session=s)
        assert len(out) == 1
        assert out[0]["user_id"] == 7
        assert out[0]["content"] == "first"
        assert out[0]["resolved"] is False
        assert "created_at" in out[0]


async def test_admin_complaints_status_filter():
    async with SessionFactory() as s:
        c1 = await feedback.record_complaint(s, 1, "open one")
        await feedback.record_complaint(s, 2, "resolved one")
        # resolve the second complaint
        all_rows = (await s.scalars(select(Complaint))).all()
        target = next(c for c in all_rows if c.content == "resolved one")
        await feedback.resolve_complaint(s, target.id)
        _ = c1
    async with SessionFactory() as s:
        opn = await admin_feedback.open_complaints(status="open", admin=None, session=s)
        res = await admin_feedback.open_complaints(status="resolved", admin=None, session=s)
        allc = await admin_feedback.open_complaints(status="all", admin=None, session=s)
    assert [c["content"] for c in opn] == ["open one"]
    assert [c["content"] for c in res] == ["resolved one"]
    assert len(allc) == 2


async def test_admin_recent_ratings_with_snippet():
    async with SessionFactory() as s:
        await feedback.record_rating(s, 1, "down", "bad answer")
        await feedback.record_rating(s, 2, "up", "good answer")
    async with SessionFactory() as s:
        downs = await admin_feedback.recent_ratings(rating="down", admin=None, session=s)
        ups = await admin_feedback.recent_ratings(rating="up", admin=None, session=s)
    assert len(downs) == 1 and downs[0]["snippet"] == "bad answer"
    assert downs[0]["rating"] == "down" and downs[0]["user_id"] == 1
    assert len(ups) == 1 and ups[0]["rating"] == "up"
