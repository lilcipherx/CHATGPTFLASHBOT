"""OpenAI text adapter (GPT-5 family). Also serves as the OpenAI-compatible base
for DeepSeek / xAI which expose the same Chat Completions schema."""
from __future__ import annotations

from collections.abc import AsyncIterator

from core.ai_router.base import Message, ProviderUnavailable, TextResult
from core.config import settings


class OpenAICompatibleText:
    """Generic OpenAI-compatible chat provider."""

    name = "openai"

    def __init__(self, api_key: str, base_url: str | None = None, name: str | None = None):
        self._api_key = api_key
        self._base_url = base_url
        if name:
            self.name = name
        self._client = None

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            # Explicit timeout so a hung upstream fails fast (and the router can fall
            # back to the next account/provider) instead of riding the SDK's 600s
            # default for a live chat turn.
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=settings.ai_request_timeout,
            )
        return self._client

    async def chat(self, messages: list[Message], model: str, **opts) -> TextResult:
        if not self.is_available():
            raise ProviderUnavailable(self.name)
        client = self._get_client()
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=opts.get("temperature", 0.7),
        )
        # FIX: U1 - defensive access: a malformed upstream response (empty choices,
        # missing message) should surface as ProviderUnavailable, not AttributeError.
        if not resp.choices:
            raise ProviderUnavailable(self.name)
        msg = getattr(resp.choices[0], "message", None)
        choice = (getattr(msg, "content", None) or "") if msg else ""
        return TextResult(
            text=choice,
            model=model,
            usage=resp.usage.model_dump() if resp.usage else {},
            # FIX: AUDIT13-M3 - an empty completion (blank / safety-filtered) is not a
            # real answer; mark ok=False so the caller refunds the consumed quota instead
            # of charging the user for a silently-empty message.
            ok=bool(choice.strip()),
        )

    async def chat_stream(
        self, messages: list[Message], model: str, **opts
    ) -> AsyncIterator[str]:
        """Yield reply text deltas as they arrive (ТЗ §3 streaming). Same auth/model
        as chat(); the caller assembles the chunks and edits the Telegram message."""
        if not self.is_available():
            raise ProviderUnavailable(self.name)
        client = self._get_client()
        stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=opts.get("temperature", 0.7),
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = getattr(chunk.choices[0].delta, "content", None)
            if delta:
                yield delta


def openai_text() -> OpenAICompatibleText:
    # Pass base_url explicitly so the SDK never inherits an ambient OPENAI_BASE_URL
    # from the process environment (which could redirect the key to a proxy).
    return OpenAICompatibleText(
        settings.openai_api_key, base_url=settings.openai_base_url, name="openai"
    )


def deepseek_text() -> OpenAICompatibleText:
    return OpenAICompatibleText(
        settings.deepseek_api_key, base_url="https://api.deepseek.com", name="deepseek"
    )


def openrouter_text() -> OpenAICompatibleText:
    return OpenAICompatibleText(
        settings.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
        name="openrouter",
    )
