"""DB-backed AI routing: pick an upstream model + an ordered list of healthy
OpenAI-compatible accounts (OmniRoute pool → fallback), and track health so a
rate-limited account is skipped for a cooldown window.

The actual HTTP call lives in core.ai_router.registry, which asks this service
for candidates and reports success/failure back here.
"""
from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from itertools import groupby

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models.ai_routing import AIAccount, AIModel

# How long an account sits in cooldown after a rate-limit / quota error.
COOLDOWN_SECONDS = 15 * 60
# Cap of consecutive errors before we hard-disable an account.
MAX_ERRORS_BEFORE_DISABLE = 20


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _over_budget(acc: AIAccount) -> bool:
    """True when a positive spend cap has been reached (ТЗ §2 «лимиты трат»)."""
    return acc.spend_limit_micros > 0 and (acc.spend_micros or 0) >= acc.spend_limit_micros


def _is_available(acc: AIAccount) -> bool:
    if not acc.enabled or not acc.api_key or not acc.base_url:
        return False
    if _over_budget(acc):
        return False
    cd = _aware(acc.cooldown_until)
    return cd is None or cd <= _now()


async def resolve_model(session: AsyncSession, key: str) -> AIModel | None:
    """Return the enabled AIModel for a logical key, or None if unknown/disabled."""
    model = await session.get(AIModel, key)
    if model is None or not model.enabled:
        return None
    return model


async def enabled_models(session: AsyncSession, modality: str = "text") -> list[AIModel]:
    """Enabled models for the /model chat keyboard, in admin-defined order.

    Search-flagged models are EXCLUDED here — they belong only to the internet-search
    (/s) picker (see ``enabled_search_models``), not the chat model list. A model with
    ``search=True`` is a web-search variant (Perplexity Sonar / *-search-preview /
    ":online") and shouldn't be pickable as a general chat model."""
    return list(
        await session.scalars(
            select(AIModel)
            .where(
                AIModel.modality == modality,
                AIModel.enabled.is_(True),
                AIModel.search.is_(False),
            )
            .order_by(AIModel.sort_order, AIModel.key)
        )
    )


async def enabled_search_models(session: AsyncSession) -> list[AIModel]:
    """Enabled models flagged for internet search (/s), in admin-defined order.
    The admin ticks `search` on a model in the AI-routing catalog; only web-capable
    upstream ids should be flagged (Perplexity Sonar, an OpenAI *-search-preview
    model, an OpenRouter ":online" variant)."""
    return list(
        await session.scalars(
            select(AIModel)
            .where(AIModel.enabled.is_(True), AIModel.search.is_(True))
            .order_by(AIModel.sort_order, AIModel.key)
        )
    )


def _weighted_order(group: list[AIAccount]) -> list[AIAccount]:
    """Order accounts that share a (tier, priority) by a weighted random shuffle so
    traffic distributes ∝ weight, while every account stays reachable as a fallback
    on exhaustion (ТЗ §2 «балансировка по весам»).

    Uses Efraimidis–Spirakis weighted sampling: key = U(0,1)**(1/weight), sorted
    descending — P(account first) ∝ its weight. A non-positive weight is clamped to 1
    (use ``enabled=False`` to take an account fully out of rotation)."""
    if len(group) <= 1:
        return group

    def _key(acc: AIAccount) -> float:
        w = acc.weight if acc.weight and acc.weight > 0 else 1
        return random.random() ** (1.0 / w)

    return sorted(group, key=_key, reverse=True)


# Admin-selectable intra-tier ordering strategy. Tier is ALWAYS primary (pool before
# fallback) so the failover guarantee holds; the strategy only reorders accounts inside
# a tier. "weighted" = priority then weight (default); "least_latency" = fastest first;
# "round_robin" = even uniform spread (ignores weight).
STRATEGIES = ("weighted", "least_latency", "round_robin")


async def get_strategy(session: AsyncSession) -> str:
    """Admin-chosen routing strategy from the `pricing` KV (key 'ai_routing'); falls
    back to 'weighted' when unset or unknown."""
    from core.models import Pricing

    row = await session.get(Pricing, "ai_routing")
    val = (row.value or {}) if row else {}
    s = val.get("strategy", "weighted")
    return s if s in STRATEGIES else "weighted"


def _order_within_tier(group: list[AIAccount], strategy: str) -> list[AIAccount]:
    if strategy == "least_latency":
        # Fastest first; unknown latency (None/0) sinks to the back.
        return sorted(group, key=lambda a: a.avg_latency_ms or 10**9)
    if strategy == "round_robin":
        g = list(group)
        random.shuffle(g)   # uniform spread, weight ignored
        return g
    # weighted (default): strict priority order, weight-balanced within a priority.
    out: list[AIAccount] = []
    for _p, pg in groupby(sorted(group, key=lambda a: a.priority), key=lambda a: a.priority):
        out.extend(_weighted_order(list(pg)))
    return out


async def candidate_accounts(
    session: AsyncSession, modality: str = "text", *, kind: str | None = None
) -> list[AIAccount]:
    """Healthy accounts for a modality, ordered OmniRoute pool → fallback.

    Tiers are always tried in order (pool before fallback) so an exhausted/limited
    pool falls through to the fallback tier and finally the direct API. Ordering
    WITHIN a tier follows the admin-selected strategy (weighted / least_latency /
    round_robin). When ``kind`` is given, only accounts of that backend kind are
    returned (e.g. pin a model to "apimart" or "kie").
    """
    stmt = select(AIAccount).where(
        AIAccount.modality == modality, AIAccount.enabled.is_(True)
    )
    if kind:
        stmt = stmt.where(AIAccount.kind == kind)
    stmt = stmt.order_by(AIAccount.tier.asc(), AIAccount.priority.asc(), AIAccount.id.asc())
    rows = [a for a in (await session.scalars(stmt)).all() if _is_available(a)]

    strategy = await get_strategy(session)
    ordered: list[AIAccount] = []
    for _tier, group in groupby(rows, key=lambda a: a.tier):   # tier primary, always
        ordered.extend(_order_within_tier(list(group), strategy))
    return ordered


async def resolve_route(session: AsyncSession, model: AIModel) -> list[AIAccount]:
    """Ordered, healthy accounts a generation for ``model`` should try, honouring
    the model's optional ``account_kind`` backend pin. Works for any modality
    (text/image/video/music) — the same pool → fallback engine for all."""
    return await candidate_accounts(session, model.modality, kind=model.account_kind)


def gateway_for_account(acc: AIAccount):
    """Build the media gateway adapter (Kie/MuAPI/APIMart…) for an account, with
    its key decrypted. Returns None for non-media kinds (text gateways like
    OmniRoute/OpenRouter are handled by the OpenAI-compatible text path)."""
    from core.ai_router.gateways import build_gateway
    from core.services.crypto import decrypt

    return build_gateway(acc.kind, decrypt(acc.api_key), acc.base_url)


async def has_accounts(session: AsyncSession) -> bool:
    """True if any account is configured at all (used to keep legacy routing when
    the admin hasn't migrated to DB-driven routing yet)."""
    return (await session.scalar(select(AIAccount.id).limit(1))) is not None


# Smoothing factor for the latency EMA: weight of the newest sample. 0.3 reacts to
# trends within a handful of requests without letting a single outlier dominate.
_LATENCY_ALPHA = 0.3


async def mark_success(
    session: AsyncSession, account: AIAccount, *,
    latency_ms: int | None = None, cost_micros: int = 0,
) -> None:
    # FIX: M3 - re-fetch the account under a row lock so concurrent mark_success /
    # mark_exhausted calls don't lose each other's counter increments via a stale
    # read-modify-write. The `account` passed in was loaded without FOR UPDATE; on
    # Postgres this serializes the writers (no-op on SQLite, which serializes writes).
    # FIX: M1 - use session.refresh to get fresh attributes under the lock (was:
    # session.scalar returned stale identity-map object without refreshing attributes).
    await session.refresh(account, with_for_update=True)
    account.total_requests += 1
    account.status = "active"
    account.cooldown_until = None
    # Accrue provider spend / себестоимость (ТЗ §2). cost_micros is the routed
    # model's admin-set per-request cost; 0 = untracked.
    if cost_micros and cost_micros > 0:
        account.spend_micros = (account.spend_micros or 0) + cost_micros
    # Reset the error counter so MAX_ERRORS_BEFORE_DISABLE counts CONSECUTIVE
    # failures (as documented), not lifetime ones — otherwise a long-lived,
    # mostly-healthy account would eventually auto-disable itself.
    account.total_errors = 0
    account.last_used_at = _now()
    # Latency is recorded only for the synchronous text path (callers that time the
    # request); media gateways long-poll and pass None, so the metric stays meaningful.
    if latency_ms is not None and latency_ms >= 0:
        account.last_latency_ms = latency_ms
        prev = account.avg_latency_ms or 0
        account.avg_latency_ms = (
            latency_ms if prev <= 0
            else round(prev * (1 - _LATENCY_ALPHA) + latency_ms * _LATENCY_ALPHA)
        )
    await session.commit()


async def mark_exhausted(
    session: AsyncSession, account: AIAccount, *, cooldown_seconds: int = COOLDOWN_SECONDS,
    error: str | None = None,
) -> None:
    """Rate-limit / quota hit — sideline the account for a cooldown window."""
    # FIX: M3 - lock the row before mutating the counters (see mark_success).
    # FIX: M1 - use session.refresh to get fresh attributes under the lock (was:
    # session.scalar returned stale identity-map object without refreshing attributes).
    await session.refresh(account, with_for_update=True)
    account.total_requests += 1
    account.total_errors += 1
    account.status = "cooldown"
    account.cooldown_until = _now() + timedelta(seconds=cooldown_seconds)
    account.last_used_at = _now()
    if error:
        account.last_error = error[:300]
    await session.commit()


async def mark_error(session: AsyncSession, account: AIAccount, error: str) -> None:
    """Non-rate-limit failure (network/5xx/auth). Disable after too many."""
    # FIX: M3 - lock the row before mutating the counters (see mark_success).
    # FIX: M1 - use session.refresh to get fresh attributes under the lock (was:
    # session.scalar returned stale identity-map object without refreshing attributes).
    await session.refresh(account, with_for_update=True)
    account.total_requests += 1
    account.total_errors += 1
    account.last_error = error[:300]
    account.last_used_at = _now()
    account.status = "error"
    if account.total_errors >= MAX_ERRORS_BEFORE_DISABLE:
        account.enabled = False
    await session.commit()
