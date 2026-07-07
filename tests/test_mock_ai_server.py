"""Contract tests for the local mock AI server (scripts/mock_ai_server).

These pin the response shapes the real upstreams use, so the bot/workers can run
end-to-end against the mock with no real keys — and so a future change to the mock
that breaks the contract is caught here. Exercised in-process via httpx
ASGITransport (no network, no running server)."""
from __future__ import annotations

import httpx
import pytest

from scripts.mock_ai_server import app

_transport = httpx.ASGITransport(app=app)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=_transport, base_url="http://mock")


@pytest.mark.asyncio
async def test_chat_completions_openai_shape():
    async with _client() as c:
        r = await c.post("/v1/chat/completions", json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
        })
    assert r.status_code == 200
    data = r.json()
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert "hi" in data["choices"][0]["message"]["content"]


@pytest.mark.asyncio
async def test_images_generations_returns_urls():
    async with _client() as c:
        r = await c.post("/v1/images/generations", json={"prompt": "a cat", "n": 2})
    data = r.json()
    assert len(data["data"]) == 2
    assert all(item["url"].startswith("http") for item in data["data"])


@pytest.mark.asyncio
async def test_moderation_flags_sentinel():
    async with _client() as c:
        clean = (await c.post("/v1/moderations", json={"input": "hello"})).json()
        bad = (await c.post("/v1/moderations", json={"input": "mock-flag-this"})).json()
    assert clean["results"][0]["flagged"] is False
    assert bad["results"][0]["flagged"] is True


@pytest.mark.asyncio
async def test_kie_job_lifecycle_completes():
    async with _client() as c:
        created = (await c.post("/api/v1/jobs/createTask",
                                json={"model": "kling-v2", "input": {}})).json()
        task_id = created["data"]["taskId"]
        rec = (await c.get("/api/v1/jobs/recordInfo", params={"taskId": task_id})).json()
    assert rec["data"]["state"] == "success"
    assert rec["data"]["resultJson"]["resultUrls"][0].startswith("http")
