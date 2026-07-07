"""Admin-controlled scheduler gate (core.services.cron_control): a job runs only when
enabled AND its interval has elapsed; the admin can toggle/retune it at runtime."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base
from core.models.cron import CronJob
from core.services import cron_control


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_claim_first_run_then_respects_interval():
    async with SessionFactory() as s:
        # first ever tick → runs, and auto-creates the row with its default interval
        assert await cron_control.claim(s, "expire_subscriptions") is True
    async with SessionFactory() as s:
        # immediately after → interval not elapsed → skipped
        assert await cron_control.claim(s, "expire_subscriptions") is False
    # rewind last_run_at beyond the interval → runs again
    async with SessionFactory() as s:
        row = await s.get(CronJob, "expire_subscriptions")
        row.last_run_at = datetime.now(UTC) - timedelta(seconds=row.interval_seconds + 1)
        await s.commit()
    async with SessionFactory() as s:
        assert await cron_control.claim(s, "expire_subscriptions") is True


async def test_disabled_job_never_runs():
    async with SessionFactory() as s:
        await cron_control.set_config(s, "prune_results", enabled=False)
    async with SessionFactory() as s:
        assert await cron_control.claim(s, "prune_results") is False


async def test_set_config_clamps_interval_and_rejects_unknown():
    async with SessionFactory() as s:
        job = await cron_control.set_config(s, "sweep_stuck_jobs", interval_seconds=1)
        assert job["interval_seconds"] == cron_control.MIN_INTERVAL  # clamped up
        job = await cron_control.set_config(s, "sweep_stuck_jobs", interval_seconds=10**9)
        assert job["interval_seconds"] == cron_control.MAX_INTERVAL  # clamped down
    async with SessionFactory() as s:
        try:
            await cron_control.set_config(s, "does_not_exist", enabled=True)
            raise AssertionError("expected KeyError for unknown job")
        except KeyError:
            pass


async def test_list_jobs_returns_all_known():
    async with SessionFactory() as s:
        jobs = await cron_control.list_jobs(s)
    assert {j["name"] for j in jobs} == set(cron_control.JOBS)
    assert all("label" in j and "enabled" in j and "interval_seconds" in j for j in jobs)
