"""AI routing: account selection order, cooldown skipping, and the OmniRoute
pool → fallback rotation in the chat() entrypoint (no network — provider mocked)."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import select

from core.ai_router import registry
from core.ai_router.base import TextResult
from core.db import SessionFactory, engine
from core.models import Base
from core.models.ai_routing import AIAccount, AIModel
from core.services import ai_routing as routing


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _seed_model(s):
    s.add(AIModel(key="m1", title="M1", upstream_model="vendor/m1", modality="text"))
    await s.commit()


class _RateLimited(Exception):
    status_code = 429


class _FakeProvider:
    """Stands in for OpenAICompatibleText: pool accounts 429, fallback succeeds."""

    def __init__(self, api_key, base_url=None, name=None):
        self.base_url = base_url or ""

    def is_available(self) -> bool:
        return True

    async def chat(self, messages, model, **opts) -> TextResult:
        if "pool" in self.base_url:
            raise _RateLimited()
        return TextResult(text="ok-fallback", model=model)


async def test_candidate_order_pool_before_fallback():
    async with SessionFactory() as s:
        await _seed_model(s)
        s.add(AIAccount(name="fb", kind="openrouter", base_url="https://fallback",
                        api_key="k", tier=1, priority=10))
        s.add(AIAccount(name="p1", kind="omniroute", base_url="https://pool1",
                        api_key="k", tier=0, priority=20))
        s.add(AIAccount(name="p2", kind="omniroute", base_url="https://pool2",
                        api_key="k", tier=0, priority=10))
        await s.commit()
        accounts = await routing.candidate_accounts(s, "text")
        # tier 0 first (ordered by priority), then tier 1
        assert [a.name for a in accounts] == ["p2", "p1", "fb"]


async def test_weighted_balancing_within_same_priority():
    async with SessionFactory() as s:
        # Two pool accounts sharing (tier 0, priority 100) — load is balanced by
        # weight: the heavy account should lead the order far more often, but BOTH
        # must always be present (every account stays reachable as a fallback).
        s.add(AIAccount(name="light", kind="omniroute", base_url="https://l",
                        api_key="k", tier=0, priority=100, weight=1))
        s.add(AIAccount(name="heavy", kind="omniroute", base_url="https://h",
                        api_key="k", tier=0, priority=100, weight=50))
        await s.commit()

        first_heavy = 0
        runs = 400
        for _ in range(runs):
            accounts = await routing.candidate_accounts(s, "text")
            assert {a.name for a in accounts} == {"light", "heavy"}  # both reachable
            if accounts[0].name == "heavy":
                first_heavy += 1
        # weight 50 vs 1 -> heavy leads ~98% of the time; a loose bound avoids flakiness.
        assert first_heavy > runs * 0.8


async def test_distinct_priority_still_strictly_ordered():
    async with SessionFactory() as s:
        # Different priorities are NOT weight-shuffled — strict priority order holds
        # regardless of weight, so an admin can still pin a hard order.
        s.add(AIAccount(name="primary", kind="omniroute", base_url="https://p",
                        api_key="k", tier=0, priority=10, weight=1))
        s.add(AIAccount(name="secondary", kind="omniroute", base_url="https://s",
                        api_key="k", tier=0, priority=20, weight=999))
        await s.commit()
        for _ in range(20):
            accounts = await routing.candidate_accounts(s, "text")
            assert [a.name for a in accounts] == ["primary", "secondary"]


async def test_over_budget_account_is_sidelined():
    async with SessionFactory() as s:
        # under cap -> routable; at/over cap -> sidelined; cap 0 -> unlimited.
        s.add(AIAccount(name="under", kind="omniroute", base_url="https://u",
                        api_key="k", tier=0, priority=100,
                        spend_micros=500, spend_limit_micros=1000))
        s.add(AIAccount(name="over", kind="omniroute", base_url="https://o",
                        api_key="k", tier=0, priority=100,
                        spend_micros=1000, spend_limit_micros=1000))
        s.add(AIAccount(name="unlimited", kind="omniroute", base_url="https://x",
                        api_key="k", tier=0, priority=100,
                        spend_micros=9_999_999, spend_limit_micros=0))
        await s.commit()
        names = {a.name for a in await routing.candidate_accounts(s, "text")}
        assert names == {"under", "unlimited"}


async def test_cooldown_account_is_skipped():
    async with SessionFactory() as s:
        await _seed_model(s)
        acc = AIAccount(name="p1", base_url="https://pool1", api_key="k", tier=0)
        s.add(acc)
        await s.commit()
        await routing.mark_exhausted(s, acc, cooldown_seconds=600)
        assert await routing.candidate_accounts(s, "text") == []


async def test_chat_falls_back_from_pool_to_openrouter(monkeypatch):
    monkeypatch.setattr(registry, "OpenAICompatibleText", _FakeProvider)
    async with SessionFactory() as s:
        await _seed_model(s)
        s.add(AIAccount(name="pool", kind="omniroute", base_url="https://pool1",
                        api_key="k", tier=0, priority=10))
        s.add(AIAccount(name="fb", kind="openrouter", base_url="https://fallback",
                        api_key="k", tier=1, priority=10))
        await s.commit()

    result = await registry.chat("m1", "привет")
    assert result.text == "ok-fallback"

    # the exhausted pool account must now be in cooldown
    async with SessionFactory() as s:
        pool = (await s.scalars(
            select(AIAccount).where(AIAccount.name == "pool")
        )).one()
        assert pool.status == "cooldown"
        assert pool.total_errors == 1


async def test_has_accounts_toggles_db_routing():
    async with SessionFactory() as s:
        assert await routing.has_accounts(s) is False
        s.add(AIAccount(name="p", base_url="https://x", api_key="k"))
        await s.commit()
        assert await routing.has_accounts(s) is True


async def test_candidate_accounts_kind_filter():
    async with SessionFactory() as s:
        s.add(AIAccount(name="omni", kind="omniroute", base_url="https://o",
                        api_key="k", modality="text", tier=0))
        s.add(AIAccount(name="orr", kind="openrouter", base_url="https://r",
                        api_key="k", modality="text", tier=1))
        await s.commit()
        # No kind → both eligible; kind pin → only the matching backend.
        assert {a.name for a in await routing.candidate_accounts(s, "text")} == {"omni", "orr"}
        pinned = await routing.candidate_accounts(s, "text", kind="openrouter")
        assert [a.name for a in pinned] == ["orr"]


async def test_resolve_route_honours_model_account_kind():
    async with SessionFactory() as s:
        s.add(AIModel(key="vid1", title="V", upstream_model="kling-v2",
                      modality="video", account_kind="kie"))
        s.add(AIAccount(name="kie", kind="kie", base_url="https://kie",
                        api_key="k", modality="video", tier=0))
        s.add(AIAccount(name="muapi", kind="muapi", base_url="https://mu",
                        api_key="k", modality="video", tier=0))
        await s.commit()
        model = await routing.resolve_model(s, "vid1")
        route = await routing.resolve_route(s, model)
        assert [a.name for a in route] == ["kie"]  # pinned to kie, muapi excluded


async def test_effective_text_cost_reads_db_then_static():
    from core.constants import TEXT_MODELS_BY_KEY
    from core.services.quota import effective_text_cost

    async with SessionFactory() as s:
        s.add(AIModel(key="m1", title="M1", upstream_model="vendor/m1",
                      modality="text", cost=4, enabled=True))
        await s.commit()
        # DB catalog cost wins (admin-editable)
        assert await effective_text_cost(s, "m1") == 4
        # not in DB -> static constants fallback
        assert await effective_text_cost(s, "gpt_5_5") == TEXT_MODELS_BY_KEY["gpt_5_5"].cost
        # unknown everywhere -> 1
        assert await effective_text_cost(s, "____nope____") == 1


async def test_mark_success_resets_consecutive_errors():
    # A mostly-healthy account must not auto-disable from lifetime errors: a single
    # success resets the counter so MAX_ERRORS_BEFORE_DISABLE counts CONSECUTIVE
    # failures (L4).
    async with SessionFactory() as s:
        acc = AIAccount(name="a", kind="kie", base_url="https://k",
                        api_key="k", modality="image", tier=0)
        s.add(acc)
        await s.commit()
        for _ in range(5):
            await routing.mark_error(s, acc, "boom")
        assert acc.total_errors == 5 and acc.enabled is True
        await routing.mark_success(s, acc)
        assert acc.total_errors == 0 and acc.status == "active"


async def test_mark_success_tracks_latency_ema():
    async with SessionFactory() as s:
        acc = AIAccount(name="a", kind="omniroute", base_url="https://o",
                        api_key="k", modality="text", tier=0)
        s.add(acc)
        await s.commit()

        # First sample seeds the average directly.
        await routing.mark_success(s, acc, latency_ms=100)
        assert acc.last_latency_ms == 100
        assert acc.avg_latency_ms == 100

        # Second sample blends in via EMA (alpha 0.3): 100*0.7 + 200*0.3 = 130.
        await routing.mark_success(s, acc, latency_ms=200)
        assert acc.last_latency_ms == 200
        assert acc.avg_latency_ms == 130

        # No latency passed (e.g. media path) leaves the metric untouched.
        await routing.mark_success(s, acc)
        assert acc.last_latency_ms == 200
        assert acc.avg_latency_ms == 130


async def test_mark_success_accrues_spend():
    async with SessionFactory() as s:
        acc = AIAccount(name="a", kind="omniroute", base_url="https://o",
                        api_key="k", modality="text", tier=0)
        s.add(acc)
        await s.commit()

        await routing.mark_success(s, acc, cost_micros=2500)   # $0.0025
        await routing.mark_success(s, acc, cost_micros=1500)   # $0.0015
        assert acc.spend_micros == 4000
        # cost 0 (untracked model) leaves spend unchanged.
        await routing.mark_success(s, acc, cost_micros=0)
        assert acc.spend_micros == 4000


# ---- intra-tier routing strategy (admin-selectable) ----
async def test_strategy_default_weighted_and_least_latency():
    """Tier is always primary (pool before fallback); within a tier the chosen
    strategy reorders. least_latency puts the fastest account first."""
    from core.models import Pricing

    now_fast, now_slow = 100, 900
    async with SessionFactory() as s:
        # two pool (tier 0) accounts, same priority, different latency
        s.add_all([
            AIAccount(id=1, name="slow", kind="omniroute", base_url="http://x/v1",
                      api_key="k", modality="text", tier=0, priority=100, weight=1,
                      enabled=True, avg_latency_ms=now_slow),
            AIAccount(id=2, name="fast", kind="omniroute", base_url="http://y/v1",
                      api_key="k", modality="text", tier=0, priority=100, weight=1,
                      enabled=True, avg_latency_ms=now_fast),
            AIAccount(id=3, name="fb", kind="openrouter", base_url="http://z/v1",
                      api_key="k", modality="text", tier=1, priority=100, weight=1,
                      enabled=True, avg_latency_ms=now_fast),
        ])
        await s.commit()

    # default (weighted): pool tier before fallback tier
    async with SessionFactory() as s:
        order = await routing.candidate_accounts(s, "text")
    assert [a.tier for a in order] == [0, 0, 1]   # tier-fallback preserved

    # least_latency: within the pool, the fast account (id=2) comes first
    async with SessionFactory() as s:
        s.add(Pricing(key="ai_routing", value={"strategy": "least_latency"}))
        await s.commit()
    async with SessionFactory() as s:
        order = await routing.candidate_accounts(s, "text")
    assert order[0].id == 2 and order[0].tier == 0   # fastest pool first
    assert order[-1].tier == 1                        # fallback still last


async def test_over_budget_account_excluded_then_next_tried():
    """A spend-capped account is filtered out so routing auto-falls to the next."""
    async with SessionFactory() as s:
        s.add_all([
            AIAccount(id=1, name="capped", kind="omniroute", base_url="http://x/v1",
                      api_key="k", modality="text", tier=0, priority=10, enabled=True,
                      spend_limit_micros=1000, spend_micros=1000),  # at cap
            AIAccount(id=2, name="ok", kind="omniroute", base_url="http://y/v1",
                      api_key="k", modality="text", tier=0, priority=20, enabled=True),
        ])
        await s.commit()
    async with SessionFactory() as s:
        order = await routing.candidate_accounts(s, "text")
    assert [a.id for a in order] == [2]   # capped one dropped, next remains
