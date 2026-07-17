"""AI-router chat() coverage — the admin-account routing path (registry._chat_via_accounts
+ _chat_with_retry + mark_exhausted). This is CLAUDE.md-hardened logic (don't reintroduce
the infinite-retry / money-leak bug) that was under-tested (registry.py ~49%). The upstream
provider is mocked so no real LLM key is needed.
"""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import select

from core.ai_router import registry
from core.ai_router.base import TextResult
from core.db import SessionFactory, engine
from core.models import Base
from core.models.ai_routing import AIAccount, AIModel


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionFactory() as s:
        s.add(AIModel(key="gpt", title="GPT", upstream_model="gpt-4",
                      modality="text", account_kind=None))
        s.add(AIAccount(name="acc1", kind="openai", base_url="http://mock/v1",
                        api_key="k", modality="text", tier=0, enabled=True))
        await s.commit()
    yield


class _OkProvider:
    def __init__(self, *a, **k):
        pass

    def is_available(self) -> bool:
        return True

    async def chat(self, messages, model_id):
        return TextResult(text="pong", model=model_id, ok=True)


class _RateLimit(Exception):
    status_code = 429  # -> _EXHAUSTED_STATUSES -> mark_exhausted


class _FailProvider:
    def __init__(self, *a, **k):
        pass

    def is_available(self) -> bool:
        return True

    async def chat(self, messages, model_id):
        raise _RateLimit("rate limited")


async def test_chat_routes_via_admin_account(monkeypatch):
    monkeypatch.setattr(registry, "OpenAICompatibleText", _OkProvider)
    res = await registry.chat("gpt", "ping", locale="en")
    assert res.ok is True
    assert res.text == "pong"


async def test_chat_marks_account_exhausted_then_falls_back(monkeypatch):
    # The only account keeps 429-ing → it must be sidelined (not retried forever),
    # and with no other account / env key the router returns a graceful ok=False.
    monkeypatch.setattr(registry, "OpenAICompatibleText", _FailProvider)
    res = await registry.chat("gpt", "ping", locale="en")
    assert res.ok is False  # graceful fallback, not an exception
    async with SessionFactory() as s:
        acc = (await s.scalars(select(AIAccount))).one()
        assert acc.total_errors > 0 or acc.last_error  # exhaustion was recorded
