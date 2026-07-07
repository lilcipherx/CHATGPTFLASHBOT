"""Perplexity adapter powering /s internet search (OpenAI-compatible API)."""
from __future__ import annotations

from core.ai_router.base import Message, ProviderUnavailable, TextResult
from core.ai_router.openai_adapter import OpenAICompatibleText
from core.config import settings


class PerplexityText(OpenAICompatibleText):
    name = "perplexity"

    def __init__(self):
        super().__init__(
            settings.perplexity_api_key,
            base_url="https://api.perplexity.ai",
            name="perplexity",
        )


async def search(query: str, model: str = "sonar") -> TextResult:
    """Run a Perplexity web search. ``model`` is the Perplexity model id (e.g.
    ``sonar`` or ``sonar-pro``); defaults to ``sonar`` for the legacy call site."""
    provider = PerplexityText()
    if not provider.is_available():
        raise ProviderUnavailable("perplexity")
    return await provider.chat([Message("user", query)], model=model or "sonar")


def perplexity_text() -> PerplexityText:
    return PerplexityText()
