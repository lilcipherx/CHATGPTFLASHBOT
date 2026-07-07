"""OpenAI TTS adapter — 12 voices (§9.4), Premium-only voice replies."""
from __future__ import annotations

from core.ai_router.base import ProviderUnavailable
from core.config import settings
from core.constants import ALL_VOICES

# OpenAI's current TTS model; voice names map 1:1 to the bot's 12 voices.
TTS_MODEL = "gpt-4o-mini-tts"


class OpenAITTS:
    name = "openai_tts"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = None

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            # Explicit base_url so the SDK never inherits an ambient OPENAI_BASE_URL;
            # explicit timeout so a hung call fails fast instead of the SDK's 600s default.
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=settings.openai_base_url,
                timeout=settings.ai_request_timeout,
            )
        return self._client

    async def speak(self, text: str, voice: str = "alloy", fmt: str = "ogg") -> bytes:
        if not self.is_available():
            raise ProviderUnavailable(self.name)
        if voice not in ALL_VOICES:
            voice = "alloy"
        client = self._get_client()
        # Telegram voice messages want OGG/Opus; OpenAI returns it directly.
        resp = await client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=text[:4000],
            response_format="opus" if fmt == "ogg" else fmt,
        )
        return await resp.aread() if hasattr(resp, "aread") else resp.read()


def tts() -> OpenAITTS:
    return OpenAITTS(settings.openai_api_key)
