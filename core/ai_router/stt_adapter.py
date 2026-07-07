"""OpenAI speech-to-text adapter — transcribes Telegram voice notes so a voice
message can be answered by the same text-chat pipeline (§30, voice input).

Mirrors tts_adapter: explicit base_url (never inherit an ambient OPENAI_BASE_URL),
graceful ProviderUnavailable when no key is configured."""
from __future__ import annotations

import io

from core.ai_router.base import ProviderUnavailable
from core.config import settings

# Current OpenAI transcription model (Whisper-class). Accepts ogg/opus directly,
# which is exactly what Telegram voice notes are.
STT_MODEL = "gpt-4o-mini-transcribe"


class OpenAISTT:
    name = "openai_stt"

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

    async def transcribe(
        self, audio: bytes, *, filename: str = "voice.ogg", locale: str | None = None
    ) -> str:
        """Return the recognised text (stripped). Empty string if nothing heard."""
        if not self.is_available():
            raise ProviderUnavailable(self.name)
        client = self._get_client()
        buf = io.BytesIO(audio)
        buf.name = filename  # the SDK infers the format from the file name
        kwargs: dict = {"model": STT_MODEL, "file": buf}
        # Bias recognition toward the user's interface language when known.
        if locale:
            kwargs["language"] = locale.split("-")[0][:2]
        resp = await client.audio.transcriptions.create(**kwargs)
        return (getattr(resp, "text", "") or "").strip()


def stt() -> OpenAISTT:
    return OpenAISTT(settings.openai_api_key)
