"""Image understanding (vision): describe / answer about a photo the user sent.

Uses OpenAI's vision-capable chat when an OpenAI key is configured; otherwise
raises ProviderUnavailable so the handler can show a graceful localized message.
"""
from __future__ import annotations

import base64

from core.ai_router.base import ProviderUnavailable, TextResult
from core.config import settings


async def describe_image(
    image_bytes: bytes, prompt: str | None = None, *, locale: str = "ru"
) -> TextResult:
    if not settings.openai_api_key:
        raise ProviderUnavailable("vision")
    from openai import AsyncOpenAI

    # Explicit base_url so the SDK never inherits an ambient OPENAI_BASE_URL;
    # explicit timeout so a hung call fails fast instead of the SDK's 600s default.
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.ai_request_timeout,
    )
    b64 = base64.b64encode(image_bytes).decode()
    user_text = prompt or (
        "Опиши это изображение подробно." if locale == "ru" else "Describe this image in detail."
    )
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",  # FIX: N2 - real vision-capable OpenAI model
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
    )
    # FIX: U2 - defensive: a malformed OpenAI vision response (empty choices /
    # missing message) should raise ProviderUnavailable, not AttributeError.
    if not resp.choices:
        raise ProviderUnavailable("vision")
    msg = getattr(resp.choices[0], "message", None)
    text = (getattr(msg, "content", None) or "") if msg else ""
    usage = resp.usage.model_dump() if resp.usage else {}
    return TextResult(text=text, model="vision", usage=usage)
