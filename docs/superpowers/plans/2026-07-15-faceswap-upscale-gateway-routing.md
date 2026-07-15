# Face Swap + Upscale Gateway Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Face Swap and Upscale workers route through the existing media-gateway pool (instead of always refunding as stubs), so an admin-added AI account activates them.

**Architecture:** Replace the stub bodies in `workers/photo_tools_tasks.py` with a shared `_run_tool_job` helper that mirrors the video worker: upload input photo(s) → `resolve_backends(modality="image")` → `submit_or_resume` → poll → `rehost_remote` → deliver → refund-on-failure. No handler, schema, or migration change.

**Tech Stack:** Python 3.11+ async, SQLAlchemy 2 async, ARQ workers, aiogram, pytest/pytest-asyncio.

## Global Constraints

- Money safety: every terminal failure (no backend / submit fail / poll failed / timeout / delivery fail) MUST mark the job `failed` AND call `refund_job(session, job)` exactly once (row-claim guard via `refunded_at`).
- Backward compatible: when no account is configured, `resolve_backends` returns `[]` → refund + notify (today's behaviour). No migration.
- ARQ-retry safe: a job with an existing `provider_job_id` must RESUME polling its owning backend, never re-submit.
- Reuse `core.services.media_dispatch` (`resolve_backends`, `submit_or_resume`) and `core.services.storage` (`save_upload`, `rehost_remote`) — do not reimplement routing.
- Follow the existing `workers/video_tasks.py` patterns exactly (conditional-UPDATE claims, poll outside the DB session).

---

### Task 1: Shared media-tool routing helper + Face Swap worker

**Files:**
- Modify: `workers/photo_tools_tasks.py` (replace the stub bodies; add helpers)
- Test: `tests/test_photo_tools_gateway.py` (create)

**Interfaces:**
- Consumes: `core.services.media_dispatch.resolve_backends(session, *, modality, model_key, params, direct_provider) -> list[Backend]`; `submit_or_resume(session, backends, *, existing_provider_job_id, existing_backend) -> tuple[Backend|None, str|None]`; `core.services.storage.save_upload(bytes, ext, *, prefix) -> str`; `storage.rehost_remote(url) -> str|None`; `core.services.refunds.refund_job(session, job)`.
- Produces: `process_faceswap_job(ctx, job_id: str) -> None`; internal `_run_tool_job(ctx, job_id, *, model_key: str, file_params: dict[str,str|None], extra_params: dict) -> None`; `_deliver_and_finalise(job_id: str, result_url: str) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_photo_tools_gateway.py`:

```python
"""Face Swap + Upscale route through the media-gateway pool: a configured backend
delivers, and every terminal failure refunds the charged image credit exactly once."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import select

from core.ai_router.base import JobStatus
from core.db import SessionFactory, engine
from core.models import Base, GenerationJob, PackBalance
from workers import photo_tools_tasks as pt


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _faceswap_job():
    async with SessionFactory() as s:
        job = GenerationJob(user_id=1, service="faceswap", status="pending",
                            pack_type="image", cost_credits=1,
                            params={"target": "tgt_fid", "source": "src_fid"})
        s.add(job)
        await s.commit()
        return job.job_id


async def _assert_failed_and_refunded(job_id, err_contains: str):
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        assert job.status == "failed"
        assert err_contains in (job.error or "")
        assert job.refunded_at is not None
        bal = (await s.execute(
            select(PackBalance).where(PackBalance.user_id == 1)
        )).scalar_one_or_none()
        assert bal is not None and bal.image_credits == 1


class _Backend:
    account_id = None
    name = "fake#1"

    def __init__(self, status: JobStatus):
        self._status = status

    async def poll(self, tid):
        return self._status


def _patch(monkeypatch, backend, *, delivered: list | None = None):
    async def _backends(*a, **k):
        return [backend] if backend else []

    async def _submit(*a, **k):
        return (backend, "tid") if backend else (None, None)

    async def _upload(file_id, job_id=None):
        return f"https://s3/{file_id}.jpg"

    async def _rehost(url, **k):
        return url

    async def _deliver(job, url, locale="ru"):
        if delivered is not None:
            delivered.append(url)

    monkeypatch.setattr(pt, "POLL_INTERVAL", 0)
    monkeypatch.setattr(pt, "resolve_backends", _backends)
    monkeypatch.setattr(pt, "submit_or_resume", _submit)
    monkeypatch.setattr(pt, "_upload_file_id", _upload)
    monkeypatch.setattr(pt, "_deliver_image", _deliver)
    import core.services.storage as storage
    monkeypatch.setattr(storage, "rehost_remote", _rehost)


async def test_faceswap_no_backend_refunds(monkeypatch):
    _patch(monkeypatch, None)
    job_id = await _faceswap_job()
    await pt.process_faceswap_job(None, job_id)
    await _assert_failed_and_refunded(job_id, "provider not configured")


async def test_faceswap_provider_failure_refunds(monkeypatch):
    _patch(monkeypatch, _Backend(JobStatus("failed", error="boom")))
    job_id = await _faceswap_job()
    await pt.process_faceswap_job(None, job_id)
    await _assert_failed_and_refunded(job_id, "boom")


async def test_faceswap_timeout_refunds(monkeypatch):
    _patch(monkeypatch, _Backend(JobStatus("processing")))
    monkeypatch.setattr(pt, "MAX_POLLS", 1)
    job_id = await _faceswap_job()
    await pt.process_faceswap_job(None, job_id)
    await _assert_failed_and_refunded(job_id, "timeout")


async def test_faceswap_success_delivers(monkeypatch):
    delivered: list = []
    _patch(monkeypatch, _Backend(JobStatus("complete", result_url="https://x/r.jpg")),
           delivered=delivered)
    job_id = await _faceswap_job()
    await pt.process_faceswap_job(None, job_id)
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        assert job.status == "complete"
        assert job.result_url == "https://x/r.jpg"
        assert job.refunded_at is None
    assert delivered == ["https://x/r.jpg"]


async def test_faceswap_missing_input_refunds(monkeypatch):
    _patch(monkeypatch, _Backend(JobStatus("processing")))
    async with SessionFactory() as s:
        job = GenerationJob(user_id=1, service="faceswap", status="pending",
                            pack_type="image", cost_credits=1, params={"target": "t"})
        s.add(job)
        await s.commit()
        job_id = job.job_id
    await pt.process_faceswap_job(None, job_id)
    await _assert_failed_and_refunded(job_id, "missing input")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_photo_tools_gateway.py -v --no-cov -p no:cacheprovider`
Expected: FAIL (AttributeError: module has no attribute `resolve_backends` / `_upload_file_id` / `POLL_INTERVAL`).

- [ ] **Step 3: Rewrite `workers/photo_tools_tasks.py`**

Replace the ENTIRE file with:

```python
"""Face Swap + Upscale workers (§15A) — route through the media-gateway pool.

Mirrors workers/video_tasks.py: upload input photo(s) → resolve_backends(image) →
submit_or_resume → poll → rehost → deliver → refund-on-failure. When no gateway
account is configured the pool is empty, so the job refunds + notifies (the previous
stub behaviour is preserved for the unconfigured case)."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy import update

from core.db import SessionFactory
from core.models import GenerationJob
from core.services.media_dispatch import resolve_backends, submit_or_resume
from core.services.refunds import refund_job

log = structlog.get_logger()

POLL_INTERVAL = 5       # seconds between polls
MAX_POLLS = 60          # ~5 min ceiling (photo tools are faster than video)


async def _notify_unavailable(user_id: int) -> None:
    """Tell the user the tool is unavailable and the credit was returned. Best-effort."""
    from core.bot_client import get_bot
    from core.i18n import t
    from core.services.users import user_locale

    try:
        async with SessionFactory() as session:
            locale = await user_locale(session, user_id)
        await get_bot().send_message(user_id, t("gen.unavailable_refund", locale))
    except Exception as exc:  # noqa: BLE001
        log.warning("notify.unavailable_failed", user_id=user_id, error=str(exc))


async def _refund_and_fail(session, job: GenerationJob, error: str) -> None:
    job.status = "failed"
    job.error = error
    job.completed_at = datetime.now(UTC)
    await refund_job(session, job)  # canonical credit/pack reversal (idempotent)
    await session.commit()


async def _upload_file_id(file_id: str, job_id: str | None = None) -> str | None:
    """Download a Telegram file_id and re-host to storage; return a fetchable URL.
    An http(s) value is passed through. Returns None on any failure."""
    if not file_id:
        return None
    try:
        if file_id.startswith(("http://", "https://")):
            return file_id
        from core.bot_client import get_bot
        from core.services import storage

        buf = await get_bot().download(file_id)
        return await storage.save_upload(buf.read(), "jpg", prefix="tool-inputs")
    except Exception as exc:  # noqa: BLE001 — a bad/expired file_id fails the job → refund
        log.warning("phototool.input_upload_failed", job_id=job_id, error=str(exc))
        return None


async def _deliver_image(job: GenerationJob, result_url: str, locale: str) -> None:
    from core.bot_client import get_bot

    await get_bot().send_photo(job.user_id, result_url)


async def _deliver_and_finalise(job_id: str, result_url: str) -> None:
    """Idempotently deliver the finished image and mark the job complete. Chat is the
    only channel for these tools, so a send failure flips the job back to failed +
    refund (parity with video_tasks' bot branch)."""
    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status == "complete":
            return
        from core.services.users import user_locale

        locale = await user_locale(session, job.user_id)
        now = datetime.now(UTC)
        claim = await session.execute(
            update(GenerationJob)
            .where(GenerationJob.job_id == job.job_id, GenerationJob.status == "processing")
            .values(status="complete", result_url=result_url, completed_at=now)
        )
        if claim.rowcount == 0:
            return  # another attempt already finalised
        await session.commit()
        try:
            await _deliver_image(job, result_url, locale)
        except Exception as exc:  # noqa: BLE001 — delivery failed after claim → refund
            async with SessionFactory() as fail_session:
                fail_job = await fail_session.get(GenerationJob, job_id)
                if fail_job is not None and fail_job.status == "complete":
                    await _refund_and_fail(fail_session, fail_job, f"deliver: {exc}")
            return


async def _run_tool_job(
    ctx, job_id: str, *, model_key: str,
    file_params: dict[str, str | None], extra_params: dict,
) -> None:
    """Shared submit→poll→deliver→refund pipeline for image tools (faceswap/upscale).

    ``file_params`` maps a provider input field → a Telegram file_id (uploaded to a
    URL before submit). ``extra_params`` are passed to the gateway verbatim."""
    # Phase A — claim, upload inputs, submit.
    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status not in ("pending", "processing"):
            return
        if job.result_url:
            await _deliver_and_finalise(job_id, job.result_url)
            return

        params = dict(extra_params)
        for field, file_id in file_params.items():
            if not file_id:
                await _refund_and_fail(session, job, f"missing input: {field}")
                return
            url = await _upload_file_id(file_id, job_id)
            if not url:
                await _refund_and_fail(session, job, f"input upload failed: {field}")
                return
            params[field] = url

        backends = await resolve_backends(
            session, modality="image", model_key=model_key,
            params=params, direct_provider=None,
        )
        backend, provider_job_id = await submit_or_resume(
            session, backends, existing_provider_job_id=job.provider_job_id,
            existing_backend=(job.params or {}).get("backend"),
        )
        if backend is None:
            await _refund_and_fail(session, job, f"{model_key} provider not configured")
            await _notify_unavailable(job.user_id)
            return

        claim = await session.execute(
            update(GenerationJob)
            .where(GenerationJob.job_id == job.job_id,
                   GenerationJob.status.in_(("pending", "processing")),
                   GenerationJob.refunded_at.is_(None))
            .values(status="processing", provider_job_id=provider_job_id,
                    params={**(job.params or {}), "backend": backend.name})
        )
        if claim.rowcount == 0:
            await session.rollback()
            return
        await session.commit()

    # Phase B — poll outside the session.
    for _ in range(MAX_POLLS):
        await asyncio.sleep(POLL_INTERVAL)
        try:
            status = await backend.poll(provider_job_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("phototool.poll_failed", job_id=job_id, error=str(exc))
            continue
        if status.status == "complete" and status.result_url:
            from core.services import storage

            result_url = await storage.rehost_remote(status.result_url) or status.result_url
            async with SessionFactory() as session:
                claim = await session.execute(
                    update(GenerationJob)
                    .where(GenerationJob.job_id == job_id, GenerationJob.status == "processing")
                    .values(result_url=result_url)
                )
                if claim.rowcount == 0:
                    return
                await session.commit()
            await _deliver_and_finalise(job_id, result_url)
            return
        if status.status == "failed":
            async with SessionFactory() as session:
                job = await session.get(GenerationJob, job_id)
                if job is None or job.status != "processing":
                    return
                await _refund_and_fail(session, job, status.error or "provider failed")
            return

    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status != "processing":
            return
        await _refund_and_fail(session, job, "timeout")


async def process_faceswap_job(ctx, job_id: str) -> None:
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        params = (job.params or {}) if job else {}
    await _run_tool_job(
        ctx, job_id, model_key="faceswap",
        file_params={"target_image": params.get("target"),
                     "source_image": params.get("source")},
        extra_params={},
    )


async def process_upscale_job(ctx, job_id: str) -> None:
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        params = (job.params or {}) if job else {}
    factor = params.get("factor", "x2")
    scale = 4 if factor == "x4" else 2
    await _run_tool_job(
        ctx, job_id, model_key="upscale",
        file_params={"image": params.get("image")},
        extra_params={"scale": scale},
    )
```

- [ ] **Step 4: Run the faceswap tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_photo_tools_gateway.py -v --no-cov -p no:cacheprovider`
Expected: all 5 tests PASS.

- [ ] **Step 5: Verify no regression in the existing photo-tool tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_phototools.py tests/test_phototool_pricing.py -v --no-cov -p no:cacheprovider`
Expected: PASS. If a test asserted the old stub error string `"faceswap provider not configured"` / `"upscale provider not configured"`, update that assertion to the new string `"faceswap provider not configured"` / `"upscale provider not configured"` (the "no backend" branch above emits `"{model_key} provider not configured"`, i.e. identical text — so no change is expected; only update if a test asserted a *different* old message).

- [ ] **Step 6: Commit**

```bash
git add workers/photo_tools_tasks.py tests/test_photo_tools_gateway.py
git commit -m "feat(tools): route Face Swap + Upscale through the media-gateway pool"
```

---

### Task 2: Upscale-specific tests

**Files:**
- Test: `tests/test_photo_tools_gateway.py` (extend)

**Interfaces:**
- Consumes: `process_upscale_job(ctx, job_id)` and the `_patch` helper from Task 1.
- Produces: nothing new (test-only).

- [ ] **Step 1: Add the failing upscale tests**

Append to `tests/test_photo_tools_gateway.py`:

```python
async def _upscale_job(factor="x2"):
    async with SessionFactory() as s:
        job = GenerationJob(user_id=1, service="upscale", status="pending",
                            pack_type="image", cost_credits=2,
                            params={"image": "img_fid", "factor": factor})
        s.add(job)
        await s.commit()
        return job.job_id


async def test_upscale_no_backend_refunds(monkeypatch):
    _patch(monkeypatch, None)
    job_id = await _upscale_job()
    await pt.process_upscale_job(None, job_id)
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        assert job.status == "failed"
        assert "provider not configured" in (job.error or "")
        assert job.refunded_at is not None
        bal = (await s.execute(
            select(PackBalance).where(PackBalance.user_id == 1)
        )).scalar_one_or_none()
        assert bal is not None and bal.image_credits == 2  # 2 credits for x2 came back


async def test_upscale_success_delivers(monkeypatch):
    delivered: list = []
    _patch(monkeypatch, _Backend(JobStatus("complete", result_url="https://x/up.jpg")),
           delivered=delivered)
    job_id = await _upscale_job("x4")
    await pt.process_upscale_job(None, job_id)
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        assert job.status == "complete"
        assert job.result_url == "https://x/up.jpg"
    assert delivered == ["https://x/up.jpg"]
```

- [ ] **Step 2: Run the upscale tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_photo_tools_gateway.py -v --no-cov -p no:cacheprovider`
Expected: all tests (faceswap + upscale) PASS.

- [ ] **Step 3: Run the full suite for regressions**

Run: `./.venv/Scripts/python.exe -m pytest tests/ --no-cov -p no:cacheprovider -q`
Expected: all pass (prior 1021 + new tests).

- [ ] **Step 4: Commit**

```bash
git add tests/test_photo_tools_gateway.py
git commit -m "test(tools): upscale gateway routing (success + no-backend refund)"
```

---

## Self-Review

- **Spec coverage:** worker-only change ✓; resolve_backends pool routing ✓; upload inputs → URL ✓; submit_or_resume + poll + rehost + deliver ✓; refund on no-backend/failed/timeout/delivery/missing-input ✓; backward compatible (empty pool → refund) ✓; no handler/schema/migration ✓; tests mirror test_worker_refunds ✓. Avatar excluded (separate spec) ✓.
- **Placeholder scan:** none — every step has full code/commands.
- **Type consistency:** `_run_tool_job(model_key, file_params, extra_params)`, `_upload_file_id(file_id, job_id)`, `_deliver_image(job, url, locale)`, `_deliver_and_finalise(job_id, result_url)` are used consistently in Tasks 1–2 and match the test monkeypatches.

## Deploy (after both tasks pass)

Per repo workflow: PR `claude/faceswap-upscale-gateway` → GitHub `main` → AWS via
`scripts/atomic_release.sh origin/main --expect-current 0044_missing_model_indexes
--expect-head 0044_missing_model_indexes` (no new migration). Then the owner adds the
`faceswap` / `upscale` AI models + gateway accounts in the admin panel to activate.
