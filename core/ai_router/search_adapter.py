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
    up = (model.upstream_model or "").lower()
    return (
        (model.account_kind or "").lower() == "perplexity"
        or up.startswith("perplexity/")
        or "sonar" in up
    )


def _perplexity_upstream(model: AIModel) -> str:
    # "perplexity/sonar-pro" -> "sonar-pro"; "sonar" -> "sonar".
    return (model.upstream_model or "sonar").split("/")[-1] or "sonar"


async def resolve_search_model(session: AsyncSession, user: User) -> AIModel | None:
    """The search model to use for this user: their saved choice if it is still an
    enabled search model, else the first enabled search model, else None (no search
    model configured — the caller falls back to Perplexity / the text model)."""
    models = await enabled_search_models(session)
    if not models:
        return None
    for m in models:
        if m.key == user.search_model:
            return m
    return models[0]


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
            return await ai_chat(model.key, query, system=system, locale=locale)
        except ProviderUnavailable:
            pass  # configured model has no key yet → fall through to the legacy path
    # Legacy fallback: real Perplexity search, else the user's own text model.
    try:
        return await perplexity_search(query)
    except ProviderUnavailable:
        return await ai_chat(user.selected_model, query, system=system, locale=locale)
