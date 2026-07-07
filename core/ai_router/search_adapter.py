"""Internet-search routing (/s): resolve the user's chosen search model and run
the query through the RIGHT web-search path.

Real web access lives in the upstream model id — a Perplexity Sonar model, an
OpenAI ``*-search-preview`` model, or an OpenRouter ``":online"`` variant — so a
search model routes through the normal chat router like any other model. The one
exception is Perplexity, which uses its own key/endpoint (it is not an
OpenAI-compatible account in the routing pool), so it goes through
``perplexity_adapter`` directly.

Admin controls the offered list by ticking ``search`` on models in the AI-routing
catalog; the user picks one (persisted in ``users.search_model``). When no search
model is configured yet, we fall back to Perplexity → the user's text model so /s
always produces an answer.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.ai_router import chat as ai_chat
from core.ai_router.base import ProviderUnavailable, TextResult
from core.ai_router.perplexity_adapter import search as perplexity_search
from core.models import User
from core.models.ai_routing import AIModel
from core.services.ai_routing import enabled_search_models


def _is_perplexity(model: AIModel) -> bool:
    # FIX: SEARCH-3 - respect an explicit admin backend pin. If account_kind is set, ONLY
    # the literal "perplexity" kind uses the direct Perplexity key — a model the admin
    # pinned to openrouter/omniroute must go through the normal account pool even if its
    # upstream id contains "sonar". Only when NO kind is pinned do we fall back to the
    # upstream-id heuristic (Perplexity ids are not OpenAI-compatible pool accounts).
    kind = (model.account_kind or "").lower()
    if kind:
        return kind == "perplexity"
    up = (model.upstream_model or "").lower()
    return up.startswith("perplexity/") or "sonar" in up


def _perplexity_upstream(model: AIModel) -> str:
    # "perplexity/sonar-pro" -> "sonar-pro"; "sonar" -> "sonar".
    return (model.upstream_model or "sonar").split("/")[-1] or "sonar"


async def resolve_search_model(
    session: AsyncSession, user: User, models: list[AIModel] | None = None
) -> AIModel | None:
    """The search model to use for this user: their saved choice if it is still an
    enabled search model THEY MAY USE, else the first usable one, else None (no usable
    search model — the caller falls back to Perplexity / the text model).

    FIX: SEARCH-1 - premium (💎) search models are filtered out for non-premium users so
    the RUN path enforces the same gate as the picker. Without this, a user whose Premium
    lapsed (their saved key still points at a paid model) — or any free user when the
    admin's first search model is premium — would keep using a paid model for free.

    FIX: SEARCH-6 - callers that already fetched the catalog pass ``models`` to avoid a
    second identical ``enabled_search_models`` query per render.
    """
    if models is None:
        models = await enabled_search_models(session)
    allowed = [m for m in models if user.is_premium or not m.premium]
    if not allowed:
        return None
    for m in allowed:
        if m.key == user.search_model:
            return m
    return allowed[0]


async def run_search(
    session: AsyncSession, user: User, query: str, system: str, locale: str = "ru"
) -> TextResult:
    """Execute the search with the resolved model, with graceful fallback so /s
    always answers even before the admin configures a search model."""
    model = await resolve_search_model(session, user)
    if model is not None:
        try:
            if _is_perplexity(model):
                return await perplexity_search(query, model=_perplexity_upstream(model))
            res = await ai_chat(model.key, query, system=system, locale=locale)
            # FIX: SEARCH-2 - ai_chat (registry.chat) NEVER raises ProviderUnavailable; it
            # returns TextResult(ok=False) when no account/provider can serve. Only return
            # a SUCCESS here — a failed configured model must fall through to the fallbacks
            # below (honouring the "always answers" contract), not surface as an error.
            if res.ok:
                return res
        except ProviderUnavailable:
            pass  # configured model has no key yet → fall through to the legacy path
    # Legacy fallback: real Perplexity search, else the user's own text model.
    try:
        res = await perplexity_search(query)
        if res.ok:
            return res
    except ProviderUnavailable:
        pass
    return await ai_chat(user.selected_model, query, system=system, locale=locale)
