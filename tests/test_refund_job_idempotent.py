"""refund_job is idempotent at the row: a generation job's charge is reversed at
most once, no matter how many callers/retries reach refund_job.

Regression for the money bug where credits.grant / packs.refund ran unconditionally,
so a second refund_job on the same job double-credited the user. Calls refund_job
directly against a real SQLite DB.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, GenerationJob, User
from core.services.refunds import refund_job


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_credits_refund_runs_once_even_if_called_twice():
    async with SessionFactory() as s:
        s.add(User(user_id=42, credits=0))
        job = GenerationJob(user_id=42, service="suno", pack_type="credits",
                            cost_credits=15, status="failed", created_at=datetime.now(UTC))
        s.add(job)
        await s.commit()
        job_id = job.job_id

        await refund_job(s, job)
        # A second call (e.g. sweep racing the worker, or a buggy double-invoke) must
        # NOT credit again.
        await refund_job(s, job)

    async with SessionFactory() as s:
        user = await s.get(User, 42)
        assert user.credits == 15  # credited exactly once
        job = await s.get(GenerationJob, job_id)
        assert job.refunded_at is not None  # the claim is recorded on the row


async def test_pack_refund_runs_once_even_if_called_twice():
    from core.models import PackBalance

    async with SessionFactory() as s:
        s.add(User(user_id=43, credits=0))
        s.add(PackBalance(user_id=43, image_credits=0))
        job = GenerationJob(user_id=43, service="kling", pack_type="image",
                            cost_credits=2, status="failed", created_at=datetime.now(UTC))
        s.add(job)
        await s.commit()
        job_id = job.job_id

        await refund_job(s, job)
        await refund_job(s, job)

    async with SessionFactory() as s:
        bal = await s.get(PackBalance, 43)
        assert bal.image_credits == 2  # pack credit returned exactly once
        job = await s.get(GenerationJob, job_id)
        assert job.refunded_at is not None


async def test_no_charge_job_does_not_burn_the_claim():
    """A job that charged nothing (no pack/credits, not free, not a Stars service)
    must NOT stamp refunded_at — otherwise the idempotency slot is spent on a no-op
    and a later corrected refund would be blocked."""
    async with SessionFactory() as s:
        s.add(User(user_id=45, credits=7))
        job = GenerationJob(user_id=45, service="suno", pack_type=None,
                            cost_credits=0, status="failed", created_at=datetime.now(UTC))
        s.add(job)
        await s.commit()
        job_id = job.job_id

        await refund_job(s, job)
        await s.commit()

    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        user = await s.get(User, 45)
        assert job.refunded_at is None   # claim untouched — nothing was charged
        assert user.credits == 7         # balance unchanged


async def test_second_refund_is_noop_across_fresh_sessions():
    """The claim survives a reload: a refund_job in one session, then another in a
    brand-new session (the real worker/sweep pattern — each opens its own session),
    still only refunds once."""
    async with SessionFactory() as s:
        s.add(User(user_id=44, credits=5))
        job = GenerationJob(user_id=44, service="suno", pack_type="credits",
                            cost_credits=10, status="failed", created_at=datetime.now(UTC))
        s.add(job)
        await s.commit()
        job_id = job.job_id
        await refund_job(s, job)

    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        await refund_job(s, job)

    async with SessionFactory() as s:
        user = await s.get(User, 44)
        assert user.credits == 15  # 5 start + 10 refunded once (not 25)
