"""Google Gemini text adapter (Gemini 3.x). Image/video (Nano Banana, Veo,
Lyria) live in the same provider family and are stubbed for later phases."""
from __future__ import annotations

from core.ai_router.base import Message, ProviderUnavailable, TextResult
from core.config import settings


class GoogleText:
    name = "google"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = None

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            from google import genai

            # Explicit timeout so a hung upstream fails fast (and the router falls
            # back) instead of the SDK's 600s default on a live chat turn. google-genai
            # takes the request timeout in MILLISECONDS via http_options.
            self._client = genai.Client(
                api_key=self._api_key,
                http_options={"timeout": settings.ai_request_timeout * 1000},
            )
        return self._client

    async def chat(self, messages: list[Message], model: str, **opts) -> TextResult:
        if not self.is_available():
            raise ProviderUnavailable(self.name)
        client = self._get_client()
        system = "\n".join(m.content for m in messages if m.role == "system") or None
        # Flatten the short rolling context into a single prompt turn.
        prompt = "\n".join(
            f"{m.role}: {m.content}" for m in messages if m.role != "system"
        )
        resp = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config={"system_instruction": system} if system else None,
        )
        # FIX: U3 - defensive: a malformed Google response (no .text attribute)
        # should surface as an empty string, not AttributeError. The router then
        # treats it as a failed turn and falls back to the next provider.
        # FIX: AI-12 - google-genai raises ValueError (NOT AttributeError) when the
        # prompt was blocked by safety filters and no candidates were returned.
        # `getattr` only catches AttributeError, so the ValueError propagated and
        # crashed the adapter. Wrap in try/except ValueError and treat as a block.
        try:
            text = getattr(resp, "text", None) or ""
        except (ValueError, AttributeError):
            # Safety block / empty candidates → return empty so the caller refunds.
            text = ""
        # FIX: AUDIT13-M3 - empty/safety-blocked reply -> ok=False so the caller refunds.
        return TextResult(text=text, model=model, ok=bool(text.strip()))


def google_text() -> GoogleText:
    return GoogleText(settings.google_api_key)
