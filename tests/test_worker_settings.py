"""Worker/beat split (M4): cron jobs live ONLY on BeatSettings, so scaling the
job-processing worker pool never fires a scheduled task more than once."""
from __future__ import annotations

from workers.main import BeatSettings, WorkerSettings


def test_worker_pool_has_no_cron():
    # the scalable job pool must NOT carry any cron jobs
    assert getattr(WorkerSettings, "cron_jobs", []) == []
    # …but it still processes the generation/broadcast jobs
    names = {getattr(f, "__name__", "") for f in WorkerSettings.functions}
    assert {
        "process_video_job", "process_music_job", "process_photoeffect_job",
        "process_avatar_job", "process_faceswap_job", "process_upscale_job",
        "run_broadcast",
    } <= names


def test_beat_owns_all_cron_jobs():
    # The scheduler is now DB-driven (admin-controlled): exactly one cron entry per
    # managed job in cron_control.JOBS, each ticking every minute and gated by its DB
    # row. NOTE: no weekly quota-reset cron — that reset is lazy per user
    # (core.services.quota._maybe_reset_weekly), so there is intentionally no
    # full-table mass UPDATE on a schedule. See workers.billing_tasks.
    from core.services.cron_control import JOBS

    assert len(BeatSettings.cron_jobs) == len(JOBS)
    # every entry wraps a managed coroutine named cron_<job>, one per JOBS key.
    coro_names = {c.coroutine.__name__ for c in BeatSettings.cron_jobs}
    assert coro_names == {f"cron_{n}" for n in JOBS}
    assert not any("reset_weekly" in n or "_reset_weekly" in n for n in coro_names)
    # beat only schedules — it must not also run the heavy job functions
    names = {getattr(f, "__name__", "") for f in BeatSettings.functions}
    assert "process_video_job" not in names


def test_beat_and_worker_use_distinct_queues():
    # Queue isolation (arq-cron-queue fix): arq's run_cron enqueues each cron record to the
    # worker's OWN queue_name, so beat MUST live on a dedicated queue or the pool would
    # dequeue unresolvable ``cron:*`` jobs ("function not found") from the shared queue.
    from core.queue import CRON_QUEUE_NAME, WORKER_QUEUE_NAME

    assert WorkerSettings.queue_name == WORKER_QUEUE_NAME == "arq:queue"
    assert BeatSettings.queue_name == CRON_QUEUE_NAME == "arq:cron"
    assert WorkerSettings.queue_name != BeatSettings.queue_name
