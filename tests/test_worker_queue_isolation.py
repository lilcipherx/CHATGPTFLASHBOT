"""Queue isolation for the beat scheduler vs the job-processing pool (arq-cron-queue fix).

arq 0.26.3 ``Worker.run_cron`` enqueues every cron record to the worker's OWN
``queue_name``. Before the fix beat and the pool shared arq's default queue, so the pool
kept dequeuing unresolvable ``cron:*`` jobs and logging "function not found" (harmless but
noisy, ~15/min). The fix isolates beat onto ``arq:cron`` and pins pool-bound work to
``arq:queue``. These tests run the REAL arq worker over fakeredis to prove:

  * a cron record enqueued to beat's queue never lands on the pool's queue;
  * the pool worker runs normal work off ``arq:queue`` and never sees / runs a cron
    (no double execution, no "function not found");
  * a cron record wrongly placed on the pool queue DOES warn (negative control — proves
    these tests go RED without the isolation);
  * the one beat-context ctx-pool dispatch (avatar sweep) targets ``arq:queue``.
"""
from __future__ import annotations

import logging

import fakeredis.aioredis
import pytest_asyncio
from arq import Worker
from arq.connections import ArqRedis

from core.db import SessionFactory, engine
from core.models import Base, GenerationJob
from core.queue import CRON_QUEUE_NAME, WORKER_QUEUE_NAME


async def _noop(*_a, **_k):  # fakeredis has no INFO command; arq only logs it
    return


def _pool() -> ArqRedis:
    fake = fakeredis.aioredis.FakeRedis()  # bytes mode (arq needs decode_responses=False)
    return ArqRedis(connection_pool=fake.connection_pool)


# arq registers a function under its __qualname__ — so worker task functions MUST be
# module-level (a nested/local def gets a "<locals>" qualname the enqueue name can't match).
_RAN = {"cron": 0, "task": 0}


async def process_demo_job(ctx):
    _RAN["task"] += 1


async def cron_sweep_stuck_jobs(ctx):  # a would-be cron fn the POOL must never run
    _RAN["cron"] += 1


class _NotFoundGrab(logging.Handler):
    """Capture arq's 'function <x> not found' worker log lines."""

    def __init__(self) -> None:
        super().__init__()
        self.hits: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if "not found" in msg:
            self.hits.append(msg)


async def _burst(pool: ArqRedis, functions, queue_name: str):
    w = Worker(
        functions=functions, redis_pool=pool, queue_name=queue_name,
        burst=True, poll_delay=0.0, max_jobs=50, handle_signals=False,
    )
    await w.main()
    return w


async def test_cron_record_isolated_to_cron_queue(monkeypatch):
    monkeypatch.setattr("arq.worker.log_redis_info", _noop)
    pool = _pool()
    # what arq's run_cron does for a beat worker whose queue_name == CRON_QUEUE_NAME:
    await pool.enqueue_job("cron_sweep_stuck_jobs",
                           _job_id="cron:cron_sweep_stuck_jobs:1",
                           _queue_name=CRON_QUEUE_NAME)
    assert await pool.zcard(CRON_QUEUE_NAME) == 1
    assert await pool.zcard(WORKER_QUEUE_NAME) == 0


async def test_pool_worker_ignores_cron_and_runs_work(monkeypatch):
    monkeypatch.setattr("arq.worker.log_redis_info", _noop)
    _RAN["cron"] = _RAN["task"] = 0
    grab = _NotFoundGrab()
    logging.getLogger("arq.worker").addHandler(grab)
    logging.getLogger("arq.worker").setLevel(logging.DEBUG)
    try:
        pool = _pool()
        # cron record on the cron queue; a real pool-bound job on the worker queue
        await pool.enqueue_job(cron_sweep_stuck_jobs.__qualname__,
                               _job_id="cron:cron_sweep_stuck_jobs:1",
                               _queue_name=CRON_QUEUE_NAME)
        await pool.enqueue_job(process_demo_job.__qualname__, _queue_name=WORKER_QUEUE_NAME)

        await _burst(pool, [process_demo_job], WORKER_QUEUE_NAME)

        assert _RAN["task"] == 1                       # pool ran the real work
        assert _RAN["cron"] == 0                       # NO double execution of the cron
        assert await pool.zcard(CRON_QUEUE_NAME) == 1  # cron queue untouched by the pool
        assert grab.hits == []                         # no "function not found"
    finally:
        logging.getLogger("arq.worker").removeHandler(grab)


async def test_cron_on_worker_queue_warns_negative_control(monkeypatch):
    """RED-guard: if a cron record reaches the pool queue (the pre-fix shape), the pool
    logs 'function not found'. Proves the isolation is what keeps the log clean."""
    monkeypatch.setattr("arq.worker.log_redis_info", _noop)
    grab = _NotFoundGrab()
    logging.getLogger("arq.worker").addHandler(grab)
    logging.getLogger("arq.worker").setLevel(logging.DEBUG)
    try:
        pool = _pool()
        await pool.enqueue_job("cron:cron_sweep_stuck_jobs",  # a name the pool can't resolve
                               _job_id="cron:cron_sweep_stuck_jobs:9",
                               _queue_name=WORKER_QUEUE_NAME)  # WRONG queue on purpose
        await _burst(pool, [process_demo_job], WORKER_QUEUE_NAME)
        assert any("not found" in h for h in grab.hits)
    finally:
        logging.getLogger("arq.worker").removeHandler(grab)


class _RecordingRedis:
    """Stand-in for ctx['redis'] that records enqueue_job calls (no real Redis)."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    async def enqueue_job(self, *args, **kwargs):
        self.calls.append((args, kwargs))


@pytest_asyncio.fixture
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_claim_pending_avatars_targets_worker_queue(_schema):
    """The only beat-context ctx-pool dispatch must pin _queue_name to the pool queue,
    else process_avatar_job would land on the cron queue and never run."""
    from workers.avatar_tasks import claim_pending_avatars

    async with SessionFactory() as s:
        s.add(GenerationJob(user_id=1, service="avatar", status="pending", params={}))
        await s.commit()

    rec = _RecordingRedis()
    n = await claim_pending_avatars({"redis": rec})

    assert n == 1
    assert len(rec.calls) == 1
    args, kwargs = rec.calls[0]
    assert args[0] == "process_avatar_job"
    assert kwargs.get("_queue_name") == WORKER_QUEUE_NAME == "arq:queue"
