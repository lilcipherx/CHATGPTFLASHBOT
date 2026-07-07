"""Admin-controlled AI routing: OpenAI-compatible accounts (OmniRoute pool +
fallback providers) and the user-selectable model catalog.

An ``AIAccount`` is any OpenAI-compatible endpoint (base_url + api_key): an
OmniRoute account, an OpenRouter key, a raw OpenAI key, etc. The router tries
accounts in (tier, priority) order, skipping those in cooldown, so a pool of
OmniRoute accounts is exhausted before falling back to OpenRouter.

An ``AIModel`` maps a logical model key (what the user picks in /model) to the
upstream model id sent to the OpenAI-compatible API.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base, TimestampMixin

# Account tiers — lower is tried first.
TIER_POOL = 0       # OmniRoute pool accounts
TIER_FALLBACK = 1   # OpenRouter / other fallbacks

# Modalities a model/account can serve. Routing matches a model to accounts of
# the same modality (text → OmniRoute/OpenRouter; image/video/music → media
# aggregators or direct provider keys).
MODALITIES = ("text", "image", "video", "music")


class AIAccount(Base, TimestampMixin):
    """One OpenAI-compatible credential the router can route a request through."""

    __tablename__ = "ai_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80))                 # "OmniRoute #1"
    # omniroute|openrouter|openai|custom
    kind: Mapped[str] = mapped_column(String(20), default="omniroute")
    base_url: Mapped[str] = mapped_column(String(300))            # OpenAI-compatible /v1 base
    api_key: Mapped[str] = mapped_column(Text)
    modality: Mapped[str] = mapped_column(String(10), default="text")   # text|image
    tier: Mapped[int] = mapped_column(Integer, default=TIER_POOL)       # 0 pool, 1 fallback
    # lower tried first within a tier
    priority: Mapped[int] = mapped_column(Integer, default=100)
    # Relative share for load-balancing across accounts that share the same
    # (tier, priority) — higher weight = more traffic (ТЗ §2 «балансировка по весам»).
    # Accounts on distinct priorities are still tried in strict priority order.
    weight: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Health / rotation state
    status: Mapped[str] = mapped_column(String(12), default="active")   # active|cooldown|error
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    total_errors: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(300))
    # Latency tracking (ТЗ §2 «latency/uptime»), synchronous text path only — media
    # gateways long-poll for minutes and would pollute the metric. avg is an
    # exponential moving average (single column, no history table).
    last_latency_ms: Mapped[int | None] = mapped_column(Integer)
    avg_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    # Accumulated provider cost / spend (ТЗ §2 «расход, себестоимость»), in micro-USD
    # (1e-6 USD) for sub-cent precision. Incremented per successful request by the
    # routed model's configured cost. Total since the last explicit spend reset (a
    # health ``reset`` does NOT clear it — spend is billing data, not health state).
    # BigInteger — grows unbounded over a busy account's lifetime.
    spend_micros: Mapped[int] = mapped_column(BigInteger, default=0)
    # Hard spend cap in micro-USD (ТЗ §2 «лимиты трат»). 0 = unlimited. When
    # 0 < spend_limit_micros <= spend_micros the account is sidelined from routing
    # until the admin resets its spend or raises the cap.
    spend_limit_micros: Mapped[int] = mapped_column(BigInteger, default=0)


class AIModel(Base):
    """A model the user can pick in /model, mapped to an upstream model id."""

    __tablename__ = "ai_models"

    # logical key, e.g. claude_4_6_sonnet
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(60))                     # shown in the keyboard
    upstream_model: Mapped[str] = mapped_column(String(120))           # id sent to the API
    modality: Mapped[str] = mapped_column(String(10), default="text")  # text|image|video|music
    # Optional backend pin: restrict this model to accounts of a given kind
    # (e.g. "omniroute", "apimart", "kie", "direct"). NULL = any enabled account
    # of the same modality (current behaviour). Lets the admin choose, per model,
    # whether it runs via a specific aggregator / direct provider.
    account_kind: Mapped[str | None] = mapped_column(String(20))
    premium: Mapped[bool] = mapped_column(Boolean, default=False)
    cost: Mapped[int] = mapped_column(Integer, default=1)   # generations charged to the user
    # Provider cost / себестоимость per request, in micro-USD (1e-6 USD) — admin-set,
    # used only for spend accounting (ТЗ §2). 0 = untracked. Distinct from ``cost``,
    # which is the credits the USER is charged.
    cost_micros: Mapped[int] = mapped_column(Integer, default=0)
    # Optional token-based provider pricing, micro-USD per 1M tokens (input/output).
    # 0 = not token-priced (use the per-request cost_micros). Powers the cost
    # calculator's token mode; LLM APIs bill per token, so this is the accurate model.
    price_in_micros: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    price_out_micros: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
