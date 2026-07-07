"""OpenRouter media gateway: image via /api/v1/images (base64) and video via the
async /api/v1/videos submit→poll flow, including the auth'd download + re-host of
the completed video (unsigned_urls need our Bearer, so the worker's plain rehost
can't fetch them)."""
from __future__ import annotations

import base64

import httpx
import pytest

from core.ai_router.base import ImageResult, ProviderUnavailable
from core.ai_router.gateways import OpenRouterMediaGateway, build_gateway


class _Resp:
    def __init__(self, json_data=None, content: bytes = b"", status: int = 200):
        self._json = json_data
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class _FakeClient:
    """Async-context httpx.AsyncClient stand-in driven by a handler(method,url,kw)."""
    def __init__(self, handler):
        self._handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kw):
        return self._handler("POST", url, kw)

    async def get(self, url, **kw):
        return self._handler("GET", url, kw)


def _patch_httpx(monkeypatch, handler):
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeClient(handler))


def _gw() -> OpenRouterMediaGateway:
    return OpenRouterMediaGateway("sk-or-test")


# ---------- registration ----------

def test_openrouter_registered_as_media_gateway():
    gw = build_gateway("openrouter", "sk-or-test")
    assert isinstance(gw, OpenRouterMediaGateway)
    assert gw.is_available()


def test_unavailable_without_key():
    assert not OpenRouterMediaGateway("").is_available()


# ---------- image: /api/v1/images returns base64 ----------

async def test_generate_image_decodes_base64(monkeypatch):
    raw = b"\x89PNG-fake-bytes"
    b64 = base64.b64encode(raw).decode()

    def handler(method, url, kw):
        assert method == "POST" and url.endswith("/images")
        assert kw["headers"]["Authorization"] == "Bearer sk-or-test"
        assert kw["json"]["model"] == "bytedance-seed/seedream-4.5"
        return _Resp({"data": [{"b64_json": b64}]})

    _patch_httpx(monkeypatch, handler)
    out = await _gw().generate_image("bytedance-seed/seedream-4.5", "a red panda", {})
    assert len(out) == 1
    assert isinstance(out[0], ImageResult)
    assert out[0].data == raw and out[0].url is None


async def test_generate_image_maps_ratio_and_count(monkeypatch):
    raw = b"x"
    b64 = base64.b64encode(raw).decode()

    def handler(method, url, kw):
        # cfg is honoured: 9:16 → portrait size, count → n (was silently dropped)
        assert kw["json"]["size"] == "1024x1536"
        assert kw["json"]["n"] == 3
        return _Resp({"data": [{"b64_json": b64}]})

    _patch_httpx(monkeypatch, handler)
    await _gw().generate_image("m", "p", {"ratio": "9:16", "count": 3})


async def test_generate_image_accepts_url_form(monkeypatch):
    _patch_httpx(monkeypatch, lambda *a: _Resp({"data": [{"url": "https://img/x.png"}]}))
    out = await _gw().generate_image("m", "p", {})
    assert out[0].url == "https://img/x.png"


async def test_generate_image_empty_raises(monkeypatch):
    _patch_httpx(monkeypatch, lambda *a: _Resp({"data": []}))
    with pytest.raises(RuntimeError):
        await _gw().generate_image("m", "p", {})


async def test_generate_image_needs_key():
    with pytest.raises(ProviderUnavailable):
        await OpenRouterMediaGateway("").generate_image("m", "p", {})


# ---------- video: submit ----------

async def test_video_submit_returns_job_id(monkeypatch):
    def handler(method, url, kw):
        assert method == "POST" and url.endswith("/videos")
        assert kw["json"]["model"] == "google/veo-3.1"
        assert kw["json"]["prompt"] == "a beach"
        assert kw["json"]["aspectRatio"] == "16:9"
        assert kw["json"]["duration"] == 8
        return _Resp({"id": "job-1", "polling_url": "x", "status": "pending"})

    _patch_httpx(monkeypatch, handler)
    tid = await _gw().submit(
        "google/veo-3.1", {"prompt": "a beach", "aspect_ratio": "16:9", "duration": 8}
    )
    assert tid == "job-1"


async def test_video_submit_no_id_raises(monkeypatch):
    _patch_httpx(monkeypatch, lambda *a: _Resp({"status": "pending"}))
    with pytest.raises(RuntimeError):
        await _gw().submit("m", {"prompt": "p"})


# ---------- video: poll ----------

async def test_video_poll_processing(monkeypatch):
    _patch_httpx(monkeypatch, lambda *a: _Resp({"status": "processing"}))
    st = await _gw().poll("job-1")
    assert st.status == "processing"


async def test_video_poll_failed(monkeypatch):
    _patch_httpx(monkeypatch, lambda *a: _Resp({"status": "failed", "error": "nsfw"}))
    st = await _gw().poll("job-1")
    assert st.status == "failed" and "nsfw" in st.error


async def test_video_poll_completed_downloads_and_rehosts(monkeypatch):
    saved = {}

    async def fake_save_upload(data, ext, *, prefix="uploads"):
        saved["data"] = data
        saved["ext"] = ext
        return "https://cdn.local/results/vid.mp4"

    from core.services import storage
    monkeypatch.setattr(storage, "save_upload", fake_save_upload)

    def handler(method, url, kw):
        if method == "GET" and url.endswith("/videos/job-1"):
            return _Resp({
                "status": "completed",
                "unsigned_urls": ["https://openrouter.ai/api/v1/videos/job-1/content?index=0"],
            })
        if method == "GET" and "content" in url:
            # the auth'd content download
            assert kw["headers"]["Authorization"] == "Bearer sk-or-test"
            return _Resp(content=b"MP4BYTES")
        raise AssertionError(f"unexpected {method} {url}")

    _patch_httpx(monkeypatch, handler)
    st = await _gw().poll("job-1")
    assert st.status == "complete"
    assert st.result_url == "https://cdn.local/results/vid.mp4"
    assert saved["data"] == b"MP4BYTES" and saved["ext"] == "mp4"


async def test_video_poll_completed_no_url_fails(monkeypatch):
    _patch_httpx(monkeypatch, lambda *a: _Resp({"status": "completed", "unsigned_urls": []}))
    st = await _gw().poll("job-1")
    assert st.status == "failed"


async def test_video_poll_download_retries_transient(monkeypatch):
    """A transient download blip is retried, not turned into a refund."""
    async def _no_sleep(_):
        return None
    monkeypatch.setattr("asyncio.sleep", _no_sleep)

    async def fake_save_upload(data, ext, *, prefix="uploads"):
        return "https://cdn.local/results/vid.mp4"

    from core.services import storage
    monkeypatch.setattr(storage, "save_upload", fake_save_upload)
    calls = {"content": 0}

    def handler(method, url, kw):
        if method == "GET" and url.endswith("/videos/job-1"):
            return _Resp({
                "status": "completed",
                "unsigned_urls": ["https://openrouter.ai/api/v1/videos/job-1/content"],
            })
        if "content" in url:
            calls["content"] += 1
            if calls["content"] == 1:
                return _Resp(status=503)   # transient upstream error
            return _Resp(content=b"MP4BYTES")
        raise AssertionError(f"unexpected {method} {url}")

    _patch_httpx(monkeypatch, handler)
    st = await _gw().poll("job-1")
    assert st.status == "complete"
    assert calls["content"] == 2   # failed once, retried, then succeeded


# ---------- storage: idempotent re-host of our own URLs ----------

def test_is_owned_url(monkeypatch):
    from core.services import storage
    assert storage.is_owned_url("/media/results/x.mp4") is True
    assert storage.is_owned_url("https://openrouter.ai/x.mp4") is False
    monkeypatch.setattr(storage.settings, "s3_public_url", "https://cdn.local")
    assert storage.is_owned_url("https://cdn.local/results/x.mp4") is True
    assert storage.is_owned_url("https://evil.com/results/x.mp4") is False


async def test_rehost_skips_our_own_url(monkeypatch):
    """rehost_remote returns an already-owned URL unchanged (no second download)."""
    from core.services import storage
    monkeypatch.setattr(storage.settings, "s3_public_url", "https://cdn.local")
    out = await storage.rehost_remote("https://cdn.local/results/vid.mp4")
    assert out == "https://cdn.local/results/vid.mp4"
