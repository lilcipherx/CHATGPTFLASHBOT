"""Generation results are re-hosted into our storage so History/Download survive the
provider URL expiring (ТЗ §13). Re-hosting is best-effort: any failure (non-http,
too big, network) falls back to the provider URL — it must never break a paid result.
"""
from __future__ import annotations

import pytest_asyncio

from core.ai_router.base import ImageResult
from core.db import SessionFactory, engine
from core.models import Base, GenerationJob, User
from core.services import storage


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


# ---- _result_ext -----------------------------------------------------------
def test_result_ext_from_content_type():
    assert storage._result_ext("http://x/a", "video/mp4") == ".mp4"
    assert storage._result_ext("http://x/a", "image/jpeg; charset=binary") == ".jpg"


def test_result_ext_falls_back_to_url_suffix():
    assert storage._result_ext("http://x/clip.webm?sig=1", None) == ".webm"
    assert storage._result_ext("http://x/no-ext", "application/octet-stream") == ".bin"


# ---- rehost_remote ---------------------------------------------------------
async def test_rehost_rejects_non_http():
    assert await storage.rehost_remote("data:image/png;base64,xxxx") is None
    assert await storage.rehost_remote("") is None


def _fake_httpx(monkeypatch, *, content: bytes, ct: str, chunk_size: int = 1 << 20,
                headers: dict | None = None, on_chunk=None):
    """Stub httpx.AsyncClient.stream() to yield ``content`` in ``chunk_size`` slices.

    rehost_remote now STREAMS the body (FIX: AUDIT-P6) so the fake mirrors that: it
    exposes .stream() returning an async-context response with .aiter_bytes(). ``on_chunk``
    (if given) is called with the running byte count as each chunk is yielded, letting a
    test assert the reader stops early instead of consuming the whole body.
    """
    import httpx

    base_headers = {"content-type": ct}
    if headers:
        base_headers.update(headers)

    class _Resp:
        is_redirect = False

        def __init__(self, url="https://prov/x.mp4"):
            self.headers = dict(base_headers)
            self.url = url

        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            total = 0
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i + chunk_size]
                total += len(chunk)
                if on_chunk is not None:
                    on_chunk(total)
                yield chunk

    class _Stream:
        def __init__(self, url):
            self._url = url

        async def __aenter__(self):
            return _Resp(self._url)

        async def __aexit__(self, *a):
            return False

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, _method, url):
            return _Stream(url)

    monkeypatch.setattr(httpx, "AsyncClient", _Client)


async def test_rehost_success_stores_and_returns_our_url(monkeypatch):
    _fake_httpx(monkeypatch, content=b"VIDEO-BYTES", ct="video/mp4")
    # This test exercises the STORE path, not SSRF — the fake host ("prov") never
    # resolves, so stub the SSRF/DNS guard (its own behaviour is covered by the
    # reject/non-http/error tests above).
    async def _no_ssrf(_url):
        return False
    monkeypatch.setattr(storage, "_is_ssrf_url_async", _no_ssrf)
    captured = {}

    async def _fake_save(data, ext, *, prefix="uploads"):
        captured["ext"] = ext
        captured["prefix"] = prefix
        return "https://our-store/results/abc.mp4"

    monkeypatch.setattr(storage, "save_upload", _fake_save)
    out = await storage.rehost_remote("https://prov/x.mp4")
    assert out == "https://our-store/results/abc.mp4"
    assert captured == {"ext": ".mp4", "prefix": "results"}


async def test_rehost_oversize_returns_none(monkeypatch):
    _fake_httpx(monkeypatch, content=b"x" * 100, ct="video/mp4")
    async def _no_ssrf(_url):
        return False
    monkeypatch.setattr(storage, "_is_ssrf_url_async", _no_ssrf)
    out = await storage.rehost_remote("https://prov/x.mp4", max_bytes=10)
    assert out is None


async def test_rehost_oversize_content_length_rejected_before_read(monkeypatch):
    """A truthful Content-Length larger than the cap is rejected WITHOUT reading a byte."""
    read_started = {"yes": False}

    def _mark(_total):
        read_started["yes"] = True

    _fake_httpx(monkeypatch, content=b"x" * 100, ct="video/mp4",
                headers={"content-length": "100"}, on_chunk=_mark)
    async def _no_ssrf(_url):
        return False
    monkeypatch.setattr(storage, "_is_ssrf_url_async", _no_ssrf)

    out = await storage.rehost_remote("https://prov/x.mp4", max_bytes=10)
    assert out is None
    assert read_started["yes"] is False  # bailed on the header, never streamed the body


async def test_rehost_stops_streaming_once_cap_exceeded(monkeypatch):
    """OOM guard: with NO Content-Length, the reader must stop the instant the running
    total passes max_bytes — it must not buffer the whole (potentially multi-GB) body."""
    seen: list[int] = []

    def _track(total):
        seen.append(total)

    # 10 chunks of 1000 bytes each, cap at 2500 → reader should abort after the 3rd chunk
    # (total 3000 > 2500) and never pull chunks 4..10.
    _fake_httpx(monkeypatch, content=b"x" * 10_000, ct="video/mp4", chunk_size=1000,
                on_chunk=_track)
    async def _no_ssrf(_url):
        return False
    monkeypatch.setattr(storage, "_is_ssrf_url_async", _no_ssrf)

    out = await storage.rehost_remote("https://prov/x.mp4", max_bytes=2500)
    assert out is None
    assert seen[-1] <= 3000  # stopped at the first chunk past the cap
    assert len(seen) == 3    # never consumed the remaining 7 chunks


async def test_rehost_swallows_errors(monkeypatch):
    import httpx

    class _Boom:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            raise RuntimeError("network down")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(httpx, "AsyncClient", _Boom)
    assert await storage.rehost_remote("https://prov/x.mp4") is None


# ---- photoeffect worker wiring --------------------------------------------
async def test_photoeffect_worker_uses_rehosted_url(monkeypatch):
    import workers.photoeffect_tasks as pe

    async with SessionFactory() as s:
        s.add(User(user_id=1, language_code="ru"))
        job = GenerationJob(
            user_id=1, service="photoeffect", model_variant="nano_banana",
            params={"prompt": "x", "preset_id": 1, "input_images": []},
            status="pending", cost_credits=0, pack_type=None,
        )
        s.add(job)
        await s.commit()
        jid = job.job_id

    async def _fake_gen(**_k):
        return [ImageResult(url="https://prov/x.png", data=None)]

    async def _fake_rehost(url, **_k):
        return "https://our-store/results/x.png"

    monkeypatch.setattr(pe, "generate_image_routed_managed", _fake_gen)
    monkeypatch.setattr(storage, "rehost_remote", _fake_rehost)

    await pe.process_photoeffect_job(None, jid)

    async with SessionFactory() as s:
        job = await s.get(GenerationJob, jid)
        assert job.status == "complete"
        assert job.result_url == "https://our-store/results/x.png"
