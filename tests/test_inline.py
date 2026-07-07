"""Inline mode (ТЗ §3): build_inline_answer covers the three branches —
hint for empty/short text, AI answer for a real query, error on a non-ok result.
Touches the DB (get_or_create_user), so it uses the same create_all + redis-aware
fixture pattern as test_promo_bonuses."""
from __future__ import annotations

import pytest_asyncio

from bot.handlers import inline
from core.ai_router.base import TextResult
from core.db import engine
from core.i18n import t
from core.models import Base
from core.services import pricing


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield
    try:
        await pricing.redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


async def test_empty_query_returns_hint():
    title, text = await inline.build_inline_answer("", 1)
    assert title == t("inline.hint_title", "ru")
    assert text == t("inline.hint_text", "ru")


async def test_short_query_returns_hint():
    title, _ = await inline.build_inline_answer("a", 1)
    assert title == t("inline.hint_title", "ru")


async def test_real_query_returns_ai_answer(monkeypatch):
    async def fake_chat(model, prompt, **kwargs):
        return TextResult(text="42", model=model, ok=True)

    monkeypatch.setattr(inline, "ai_chat", fake_chat)
    title, text = await inline.build_inline_answer("сколько будет 6*7", 1)
    assert title == "сколько будет 6*7"
    assert text == "42"


async def test_failed_result_returns_error(monkeypatch):
    async def fake_chat(model, prompt, **kwargs):
        return TextResult(text="provider down", model=model, ok=False)

    monkeypatch.setattr(inline, "ai_chat", fake_chat)
    title, text = await inline.build_inline_answer("any question", 1)
    assert title == t("inline.error_title", "ru")
    assert text == t("inline.error_text", "ru")


async def test_banned_user_is_blocked(monkeypatch):
    """Inline bypasses BanMiddleware, so build_inline_answer must enforce the ban
    itself: a banned user gets the error article and the AI is never called."""
    from core.db import SessionFactory
    from core.models import User

    called = {"n": 0}

    async def fake_chat(model, prompt, **kwargs):
        called["n"] += 1
        return TextResult(text="should-not-happen", model=model, ok=True)

    monkeypatch.setattr(inline, "ai_chat", fake_chat)

    async with SessionFactory() as s:
        s.add(User(user_id=555, language_code="ru", is_banned=True))
        await s.commit()

    title, _ = await inline.build_inline_answer("a real question", 555)
    assert title == t("inline.error_title", "ru")
    assert called["n"] == 0  # banned → AI never invoked


async def test_inline_ai_is_rate_limited(monkeypatch):
    """Inline AI is free + bypasses the message throttle, so a per-user cap must gate
    the AI call: once the window limit is hit, further queries return the throttle
    hint without invoking the model (anti-abuse against unmetered spam)."""
    calls = {"n": 0}

    async def fake_chat(model, prompt, **kwargs):
        calls["n"] += 1
        return TextResult(text="ok", model=model, ok=True)

    monkeypatch.setattr(inline, "ai_chat", fake_chat)
    monkeypatch.setattr(inline, "INLINE_RL_LIMIT", 2)

    uid = 778899  # unique id so the fixed-window counter is isolated
    results = [await inline.build_inline_answer("a real question", uid) for _ in range(4)]

    assert calls["n"] == 2  # only the first two queries reached the AI
    assert results[2][0] == t("inline.throttle_title", "ru")
    assert results[3][0] == t("inline.throttle_title", "ru")
