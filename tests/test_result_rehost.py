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


def _fake_httpx(monkeypatch, *, content: bytes, ct: str):
    import httpx

    class _Resp:
        # FIX: AUDIT-TEST - include `url` — rehost_remote re-checks resp.url after
        # redirects (FIX: F8); the old fake lacked it → AttributeError → rehost None.
        def __init__(self, url="https://prov/x.mp4"):
            self.content = content
            self.headers = {"content-type": ct}
            self.url = url

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, _url):
            return _Resp(_url)

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
    out = await storage.rehost_remote("https://prov/x.mp4", max_bytes=10)
    assert out is None


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
