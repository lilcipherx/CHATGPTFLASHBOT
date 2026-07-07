"""Anthropic text adapter (Claude 4.x)."""
from __future__ import annotations

from core.ai_router.base import Message, ProviderUnavailable, TextResult
from core.config import settings


class AnthropicText:
    name = "anthropic"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = None

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic

            # Explicit timeout so a hung upstream fails fast (and the router falls
            # back) instead of the SDK's 600s default on a live chat turn.
            self._client = AsyncAnthropic(
                api_key=self._api_key, timeout=settings.ai_request_timeout
            )
        return self._client

    async def chat(self, messages: list[Message], model: str, **opts) -> TextResult:
        if not self.is_available():
            raise ProviderUnavailable(self.name)
        client = self._get_client()
        system = "\n".join(m.content for m in messages if m.role == "system") or None
        convo = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        resp = await client.messages.create(
            model=model,
            system=system,
            messages=convo,
            max_tokens=opts.get("max_tokens", 4096),
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        # FIX: FINAL-7 / AUDIT12-22 - Anthropic can return usage=None on safety-blocked
        # responses; calling .model_dump() then raises AttributeError mid-reply.
        # Wrap in try/except for defensive parity with OpenAI adapter.
        try:
            usage = resp.usage.model_dump() if resp.usage is not None else {}
        except Exception:  # noqa: BLE001
            usage = {}
        # FIX: AUDIT13-M3 - empty/safety-blocked reply -> ok=False so the caller refunds.
        return TextResult(text=text, model=model, usage=usage, ok=bool(text.strip()))


def anthropic_text() -> AnthropicText:
    return AnthropicText(settings.anthropic_api_key)
