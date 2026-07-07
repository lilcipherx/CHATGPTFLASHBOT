"""Verify a real AI provider end-to-end with your key.

    # set the key first, then:
    OPENAI_API_KEY=sk-... python -m scripts.live_check openai
    GOOGLE_API_KEY=...    python -m scripts.live_check google

Uses a real, currently-available model id (not the bot's fictional GPT-5.5/
Gemini-3.x labels) so you can confirm the adapter talks to the live API.
"""
from __future__ import annotations

import asyncio
import sys

from core.ai_router.base import Message
from core.ai_router.google_adapter import google_text
from core.ai_router.openai_adapter import openai_text

PROMPT = "Ответь одним предложением: ты на связи?"

# real model ids for the live check (override via argv[2])
REAL_MODELS = {"openai": "gpt-4o-mini", "google": "gemini-1.5-flash"}


async def main(provider_name: str, model: str | None) -> None:
    provider = {"openai": openai_text, "google": google_text}[provider_name]()
    if not provider.is_available():
        raise SystemExit(f"❌ No API key configured for {provider_name}.")
    model = model or REAL_MODELS[provider_name]
    print(f"→ {provider_name} / {model}")
    res = await provider.chat([Message("user", PROMPT)], model)
    print("✅ Live response:\n", res.text)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in REAL_MODELS:
        raise SystemExit("usage: python -m scripts.live_check <openai|google> [model]")
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
