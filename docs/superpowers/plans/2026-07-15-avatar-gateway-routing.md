# Avatar Gateway Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Avatar worker generate through the media-gateway pool (instead of always refunding as a stub), delivering the ~100 result images to chat as Telegram albums and refunding the Stars purchase only on genuine failure.

**Architecture:** Add additive multi-URL support to `JobStatus` + the gateways, then rewrite `workers/avatar_tasks.py` to mirror the video/faceswap pattern (`resolve_backends` → `submit_or_resume` → poll → collect URLs → deliver albums → refund-on-failure).

**Tech Stack:** Python 3.11+ async, SQLAlchemy 2 async, ARQ workers, aiogram, pytest/pytest-asyncio.

## Global Constraints

- Money safety: every terminal failure (no backend / submit fail / provider failed / timeout / zero URLs / nothing delivered) MUST mark the job `failed` AND call `refund_job(session, job)` (which routes avatar → `refund_stars`, money-first, idempotent on the tx, keyed by `charge_id`).
- Backward compatible: no account configured → `resolve_backends` returns `[]` → refund Stars (today's behaviour). `JobStatus.result_urls` is additive (default `[]`); single-image callers keep using `result_url`.
- ARQ-retry safe: a job with an existing `provider_job_id` RESUMES its owning backend, never re-submits.
- Reuse `core.services.media_dispatch`, `core.services.storage`, `core.services.refunds.refund_job`. Follow `workers/video_tasks.py` patterns (conditional-UPDATE claims, poll outside the session).
- Keep the existing `claim_pending_avatars` cron unchanged.

---

### Task 1: Multi-URL result support (JobStatus + gateways)

**Files:**
- Modify: `core/ai_router/base.py` (add `JobStatus.result_urls`)
- Modify: `core/ai_router/gateways.py` (add `_result_urls`; populate in Kie + MuAPI)
- Test: `tests/test_gateway_result_urls.py` (create)

**Interfaces:**
- Produces: `JobStatus(status, result_url=None, error=None, result_urls: list[str]=[])`; `core.ai_router.gateways._result_urls(obj) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gateway_result_urls.py`:

```python
"""Multi-URL result support: JobStatus.result_urls default + gateways._result_urls
collector + Kie/MuAPI populate all image URLs on a complete task."""
from __future__ import annotations

from core.ai_router.base import JobStatus
from core.ai_router.gateways import KieGateway, MuapiGateway, _result_urls


def test_jobstatus_result_urls_defaults_empty():
    js = JobStatus("complete", result_url="https://x/1.png")
    assert js.result_urls == []


def test_result_urls_collects_all_dedup_ordered():
    obj = {"resultUrls": ["https://a/1.png", "https://a/2.png", "https://a/1.png"],
           "misc": {"thumb": "https://a/3.png"}}
    assert _result_urls(obj) == ["https://a/1.png", "https://a/2.png", "https://a/3.png"]


def test_result_urls_empty_when_none():
    assert _result_urls({"state": "success", "n": 5}) == []


def test_kie_complete_populates_result_urls():
    data = {"state": "success",
            "resultJson": {"resultUrls": ["https://k/1.png", "https://k/2.png"]}}
    js = KieGateway._to_status(data)
    assert js.status == "complete"
    assert js.result_url == "https://k/1.png"
    assert js.result_urls == ["https://k/1.png", "https://k/2.png"]


def test_muapi_complete_populates_result_urls():
    data = {"status": "completed",
            "outputs": ["https://m/1.png", "https://m/2.png", "https://m/3.png"]}
    js = MuapiGateway._to_status(data)
    assert js.status == "complete"
    assert js.result_urls == ["https://m/1.png", "https://m/2.png", "https://m/3.png"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_gateway_result_urls.py -v --no-cov -p no:cacheprovider`
Expected: FAIL (`_result_urls` not importable; `result_urls` attr missing).

- [ ] **Step 3: Add `result_urls` to `JobStatus`**

In `core/ai_router/base.py`, change the `JobStatus` dataclass to:

```python
@dataclass
class JobStatus:
    status: str  # pending | processing | complete | failed
    result_url: str | None = None
    error: str | None = None
    # Additive: ALL result URLs for multi-image jobs (avatar). Single-image callers
    # keep using result_url (== result_urls[0] when populated).
    result_urls: list[str] = field(default_factory=list)
```

(`field` is already imported at the top of the file.)

- [ ] **Step 4: Add `_result_urls` + populate Kie/MuAPI in `core/ai_router/gateways.py`**

Add after the existing `_result_url` function:

```python
def _result_urls(obj: Any) -> list[str]:
    """ALL http(s) URLs in the result, order-preserving + de-duplicated. Prefers the
    known result-key subtrees (so previews elsewhere don't intrude), else a full walk.
    Used for multi-image results (avatar)."""
    out: list[str] = []

    def _walk(o: Any) -> None:
        if isinstance(o, str):
            if o.startswith("http") and o not in out:
                out.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                _walk(v)
        elif isinstance(o, list):
            for v in o:
                _walk(v)

    if isinstance(obj, dict):
        for key in _RESULT_KEYS:
            if key in obj:
                _walk(obj[key])
    if not out:
        _walk(obj)
    return out
```

In `KieGateway._to_status`, the `complete` branch — replace:

```python
            url = _result_url(parsed)
            if url:
                return JobStatus("complete", result_url=url)
            return JobStatus("failed", error="kie: no result url")
```

with:

```python
            url = _result_url(parsed)
            urls = _result_urls(parsed)
            if url:
                return JobStatus("complete", result_url=url, result_urls=urls)
            return JobStatus("failed", error="kie: no result url")
```

In `MuapiGateway._to_status`, the `complete` branch — replace:

```python
            url = _result_url(payload)
            if url:
                return JobStatus("complete", result_url=url)
            return JobStatus("failed", error="muapi: no result url")
```

with:

```python
            url = _result_url(payload)
            urls = _result_urls(payload)
            if url:
                return JobStatus("complete", result_url=url, result_urls=urls)
            return JobStatus("failed", error="muapi: no result url")
```

- [ ] **Step 5: Run to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_gateway_result_urls.py -v --no-cov -p no:cacheprovider`
Expected: all 5 PASS.

- [ ] **Step 6: Run gateway/video regression (single-URL callers unchanged)**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_media_dispatch.py tests/test_video.py tests/test_worker_refunds.py -q --no-cov -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add core/ai_router/base.py core/ai_router/gateways.py tests/test_gateway_result_urls.py
git commit -m "feat(gateways): additive JobStatus.result_urls + multi-URL collector"
```

---

### Task 2: Avatar worker via the gateway pool + album delivery

**Files:**
- Modify: `workers/avatar_tasks.py` (rewrite `process_avatar_job`; keep `claim_pending_avatars`)
- Test: `tests/test_avatar_gateway.py` (create)

**Interfaces:**
- Consumes: `resolve_backends`, `submit_or_resume` (Task-1 `JobStatus.result_urls`), `storage.save_upload`/`rehost_remote`, `refund_job`.
- Produces: `process_avatar_job(ctx, job_id: str) -> None`; internal `_deliver_albums(user_id: int, urls: list[str]) -> int`; `_upload_file_id(file_id, job_id=None) -> str|None`; `_refund_and_fail(session, job, error)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_avatar_gateway.py`:

```python
"""Avatar routes through the media-gateway pool: a configured backend delivers the
result images as albums; every terminal failure marks the job failed + refunds."""
from __future__ import annotations

import pytest_asyncio

from core.ai_router.base import JobStatus
from core.db import SessionFactory, engine
from core.models import Base, GenerationJob
from workers import avatar_tasks as at


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _avatar_job(count=3):
    async with SessionFactory() as s:
        job = GenerationJob(user_id=1, service="avatar", status="pending",
                            pack_type="stars", cost_credits=0,
                            params={"selfie_file_id": "self_fid", "count": count,
                                    "charge_id": "ch_1"})
        s.add(job)
        await s.commit()
        return job.job_id


class _Backend:
    account_id = None
    name = "fake#1"

    def __init__(self, status: JobStatus):
        self._status = status

    async def poll(self, tid):
        return self._status


def _patch(monkeypatch, backend, *, delivered: list | None = None, refunds: list | None = None):
    async def _backends(*a, **k):
        return [backend] if backend else []

    async def _submit(*a, **k):
        return (backend, "tid") if backend else (None, None)

    async def _upload(file_id, job_id=None):
        return f"https://s3/{file_id}.jpg"

    async def _rehost(url, **k):
        return url

    async def _albums(user_id, urls):
        if delivered is not None:
            delivered.extend(urls)
        return len(urls)

    async def _refund(session, job):
        if refunds is not None:
            refunds.append(job.job_id)

    monkeypatch.setattr(at, "POLL_INTERVAL", 0)
    monkeypatch.setattr(at, "resolve_backends", _backends)
    monkeypatch.setattr(at, "submit_or_resume", _submit)
    monkeypatch.setattr(at, "_upload_file_id", _upload)
    monkeypatch.setattr(at, "_deliver_albums", _albums)
    monkeypatch.setattr(at, "refund_job", _refund)
    import core.services.storage as storage
    monkeypatch.setattr(storage, "rehost_remote", _rehost)


async def _assert_failed_refunded(job_id, refunds, err_contains):
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        assert job.status == "failed"
        assert err_contains in (job.error or "")
    assert job_id in refunds


async def test_avatar_success_multi_url_delivers(monkeypatch):
    delivered: list = []
    _patch(monkeypatch, _Backend(JobStatus("complete", result_url="https://a/1.png",
           result_urls=["https://a/1.png", "https://a/2.png"])), delivered=delivered)
    job_id = await _avatar_job()
    await at.process_avatar_job(None, job_id)
    async with SessionFactory() as s:
        job = await s.get(GenerationJob, job_id)
        assert job.status == "complete"
    assert delivered == ["https://a/1.png", "https://a/2.png"]


async def test_avatar_success_single_url_delivers(monkeypatch):
    delivered: list = []
    _patch(monkeypatch, _Backend(JobStatus("complete", result_url="https://a/only.png")),
           delivered=delivered)
    job_id = await _avatar_job()
    await at.process_avatar_job(None, job_id)
    assert delivered == ["https://a/only.png"]


async def test_avatar_no_backend_refunds(monkeypatch):
    refunds: list = []
    _patch(monkeypatch, None, refunds=refunds)
    job_id = await _avatar_job()
    await at.process_avatar_job(None, job_id)
    await _assert_failed_refunded(job_id, refunds, "provider not configured")


async def test_avatar_provider_failed_refunds(monkeypatch):
    refunds: list = []
    _patch(monkeypatch, _Backend(JobStatus("failed", error="boom")), refunds=refunds)
    job_id = await _avatar_job()
    await at.process_avatar_job(None, job_id)
    await _assert_failed_refunded(job_id, refunds, "boom")


async def test_avatar_timeout_refunds(monkeypatch):
    refunds: list = []
    _patch(monkeypatch, _Backend(JobStatus("processing")), refunds=refunds)
    monkeypatch.setattr(at, "MAX_POLLS", 1)
    job_id = await _avatar_job()
    await at.process_avatar_job(None, job_id)
    await _assert_failed_refunded(job_id, refunds, "timeout")


async def test_avatar_complete_zero_urls_refunds(monkeypatch):
    refunds: list = []
    _patch(monkeypatch, _Backend(JobStatus("complete")), refunds=refunds)
    job_id = await _avatar_job()
    await at.process_avatar_job(None, job_id)
    await _assert_failed_refunded(job_id, refunds, "no results")


async def test_avatar_missing_selfie_refunds(monkeypatch):
    refunds: list = []
    _patch(monkeypatch, _Backend(JobStatus("processing")), refunds=refunds)
    async with SessionFactory() as s:
        job = GenerationJob(user_id=1, service="avatar", status="pending",
                            pack_type="stars", cost_credits=0,
                            params={"count": 3, "charge_id": "ch_1"})
        s.add(job)
        await s.commit()
        job_id = job.job_id
    await at.process_avatar_job(None, job_id)
    await _assert_failed_refunded(job_id, refunds, "missing selfie")
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_avatar_gateway.py -v --no-cov -p no:cacheprovider`
Expected: FAIL (`POLL_INTERVAL` / `_deliver_albums` / `resolve_backends` not attributes of the current stub module).

- [ ] **Step 3: Rewrite `workers/avatar_tasks.py`**

Replace the ENTIRE file with:

```python
"""Avatar generation worker (§3.1) — route through the media-gateway pool.

Mirrors workers/video_tasks.py: upload the selfie → resolve_backends(image) →
submit_or_resume → poll → collect ALL result URLs → deliver as Telegram albums →
refund the Stars purchase on genuine failure. When no gateway account is configured
the pool is empty, so the Stars purchase is refunded (previous stub behaviour)."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update

from core.db import SessionFactory
from core.models import GenerationJob
from core.queue import WORKER_QUEUE_NAME
from core.services.media_dispatch import resolve_backends, submit_or_resume
from core.services.refunds import refund_job

log = structlog.get_logger()

POLL_INTERVAL = 10       # seconds between polls
MAX_POLLS = 120          # ~20 min ceiling (avatar training is slow)
ALBUM_SIZE = 10          # Telegram media-group max


async def _notify_unavailable(user_id: int) -> None:
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
    await refund_job(session, job)  # avatar → refund_stars (money-first, idempotent)
    await session.commit()


async def _upload_file_id(file_id: str, job_id: str | None = None) -> str | None:
    if not file_id:
        return None
    try:
        if file_id.startswith(("http://", "https://")):
            return file_id
        from core.bot_client import get_bot
        from core.services import storage

        buf = await get_bot().download(file_id)
        return await storage.save_upload(buf.read(), "jpg", prefix="avatar-inputs")
    except Exception as exc:  # noqa: BLE001
        log.warning("avatar.selfie_upload_failed", job_id=job_id, error=str(exc))
        return None


async def _deliver_albums(user_id: int, urls: list[str]) -> int:
    """Send urls to chat in media groups of ALBUM_SIZE. Returns how many were sent.
    Best-effort per album so one bad group doesn't drop the rest."""
    from aiogram.types import InputMediaPhoto

    from core.bot_client import get_bot

    bot = get_bot()
    sent = 0
    for i in range(0, len(urls), ALBUM_SIZE):
        chunk = urls[i:i + ALBUM_SIZE]
        try:
            await bot.send_media_group(user_id, [InputMediaPhoto(media=u) for u in chunk])
            sent += len(chunk)
        except Exception as exc:  # noqa: BLE001 — a bad album must not drop the rest
            log.warning("avatar.album_send_failed", user_id=user_id, error=str(exc))
        await asyncio.sleep(1)  # ease Telegram rate limits between albums
    return sent


async def process_avatar_job(ctx, job_id: str) -> None:
    # Phase A — claim, upload selfie, submit.
    async with SessionFactory() as session:
        job = await session.get(GenerationJob, job_id)
        if job is None or job.status not in ("pending", "processing"):
            return
        row = job.params or {}
        selfie = row.get("selfie_file_id")
        count = int(row.get("count") or 1)
        if not selfie:
            await _refund_and_fail(session, job, "missing selfie")
            return
        url = await _upload_file_id(selfie, job_id)
        if not url:
            await _refund_and_fail(session, job, "selfie upload failed")
            return

        backends = await resolve_backends(
            session, modality="image", model_key="avatar",
            params={"image": url, "count": count}, direct_provider=None,
        )
        backend, provider_job_id = await submit_or_resume(
            session, backends, existing_provider_job_id=job.provider_job_id,
            existing_backend=row.get("backend"),
        )
        if backend is None:
            await _refund_and_fail(session, job, "avatar provider not configured")
            await _notify_unavailable(job.user_id)
            return

        claim = await session.execute(
            update(GenerationJob)
            .where(GenerationJob.job_id == job.job_id,
                   GenerationJob.status.in_(("pending", "processing")),
                   GenerationJob.refunded_at.is_(None))
            .values(status="processing", provider_job_id=provider_job_id,
                    params={**row, "backend": backend.name})
        )
        if claim.rowcount == 0:
            await session.rollback()
            return
        await session.commit()
        user_id = job.user_id

    # Phase B — poll outside the session.
    for _ in range(MAX_POLLS):
        await asyncio.sleep(POLL_INTERVAL)
        try:
            status = await backend.poll(provider_job_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("avatar.poll_failed", job_id=job_id, error=str(exc))
            continue
        if status.status == "complete":
            urls = list(status.result_urls) or (
                [status.result_url] if status.result_url else [])
            if not urls:
                async with SessionFactory() as session:
                    job = await session.get(GenerationJob, job_id)
                    if job is None or job.status != "processing":
                        return
                    await _refund_and_fail(session, job, "avatar: no results")
                return
            from core.services import storage

            final = [await storage.rehost_remote(u) or u for u in urls]
            async with SessionFactory() as session:
                job = await session.get(GenerationJob, job_id)
                if job is None or job.status != "processing":
                    return
                claim = await session.execute(
                    update(GenerationJob)
                    .where(GenerationJob.job_id == job_id, GenerationJob.status == "processing")
                    .values(status="complete", result_url=final[0],
                            completed_at=datetime.now(UTC))
                )
                if claim.rowcount == 0:
                    return
                await session.commit()
            delivered = await _deliver_albums(user_id, final)
            if delivered == 0:
                async with SessionFactory() as fail_session:
                    fail_job = await fail_session.get(GenerationJob, job_id)
                    if fail_job is not None and fail_job.status == "complete":
                        await _refund_and_fail(fail_session, fail_job, "avatar: delivery failed")
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


async def claim_pending_avatars(ctx) -> int:
    """Cron sweep: enqueue any pending avatar jobs (e.g. after a restart) so a stuck
    purchase is processed (and, until a provider exists, refunded)."""
    async with SessionFactory() as session:
        rows = (
            await session.scalars(
                select(GenerationJob).where(
                    GenerationJob.service == "avatar",
                    GenerationJob.status == "pending",
                )
            )
        ).all()
        for job in rows:
            await ctx["redis"].enqueue_job(
                "process_avatar_job", str(job.job_id), _queue_name=WORKER_QUEUE_NAME
            )
        return len(rows)
```

- [ ] **Step 4: Run the avatar tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_avatar_gateway.py -v --no-cov -p no:cacheprovider`
Expected: all 7 PASS.

- [ ] **Step 5: Verify worker-registration + avatar regressions**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_worker_settings.py -q --no-cov -p no:cacheprovider`
Expected: PASS (`process_avatar_job` + `claim_pending_avatars` still registered).

- [ ] **Step 6: Full suite for regressions**

Run: `./.venv/Scripts/python.exe -m pytest tests/ --no-cov -p no:cacheprovider -q`
Expected: all pass (prior 1028 + new tests).

- [ ] **Step 7: Commit**

```bash
git add workers/avatar_tasks.py tests/test_avatar_gateway.py
git commit -m "feat(avatar): route through the media-gateway pool with album delivery"
```

---

## Self-Review

- **Spec coverage:** additive `result_urls` ✓; `_result_urls` collector + Kie/MuAPI populate ✓; avatar worker pool routing ✓; selfie upload → URL ✓; submit_or_resume + poll ✓; multi-URL collect + rehost ✓; album delivery (chunk 10, throttle) ✓; refund on no-backend/failed/timeout/zero-URLs/missing-selfie/nothing-delivered ✓; Stars via refund_job ✓; claim_pending_avatars preserved ✓; backward compatible ✓; no migration ✓.
- **Placeholder scan:** none — every step has full code/commands.
- **Type consistency:** `JobStatus(..., result_urls=[])`; `_result_urls(obj)->list[str]`; `_deliver_albums(user_id, urls)->int`; `_upload_file_id(file_id, job_id)`; `refund_job(session, job)` — used consistently across tasks and test monkeypatches.

## Deploy (after both tasks pass)

PR `claude/avatar-gateway` → GitHub `main` → AWS via `scripts/atomic_release.sh
origin/main --expect-current 0044_missing_model_indexes --expect-head
0044_missing_model_indexes` (no migration). Owner then adds the `avatar` AI model +
gateway account in admin to activate.
