"""Seed the AIModel catalog from the static TEXT_MODELS list so the bot's /model
keyboard and the admin panel have a starting point. Upstream ids use the common
OpenRouter-style ``provider/model`` slug — edit them in the admin panel to match
whatever OmniRoute expects.

    python -m scripts.seed_ai_models
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import func, select

from core.constants import TEXT_MODELS
from core.db import SessionFactory
from core.models.ai_routing import AIModel

# logical key -> upstream model id sent to the OpenAI-compatible gateway
# FIX: AI-2 - replaced fictional model IDs with REAL provider model IDs so
# auto-seed on first deploy doesn't break admin-account routing with 400
# model_not_found. These match the IDs in core/ai_router/registry.py
# (_TEXT_ROUTES / _OPENROUTER_PAID_MODELS) so legacy env-key routing and
# DB-routed accounts hit the same upstream model.
_UPSTREAM = {
    "gpt_5_5": "openai/gpt-4o",                       # was: openai/gpt-5.5 (fictional)
    "gpt_5_4": "openai/gpt-4o-mini",                  # was: openai/gpt-5.4 (fictional)
    "gpt_5_mini": "openai/gpt-4o-mini",               # was: openai/gpt-5-mini (fictional)
    "claude_4_8_opus": "anthropic/claude-3-5-sonnet", # was: anthropic/claude-opus-4-8 (fictional)
    "claude_4_6_sonnet": "anthropic/claude-3-5-haiku",# was: anthropic/claude-sonnet-4-6 (fictional)
    "deepseek_v4_pro": "deepseek/deepseek-reasoner",  # already real
    "deepseek_v4": "deepseek/deepseek-chat",          # already real
    "gemini_3_5_flash": "google/gemini-1.5-flash",    # was: google/gemini-3.5-flash (fictional)
    "gemini_3_1_flash": "google/gemini-1.5-pro",      # was: google/gemini-3.1-flash (fictional)
}


async def main(force: bool = False) -> None:
    async with SessionFactory() as session:
        # Safe to wire into the deploy: only seed an EMPTY catalog (first boot), so
        # re-running on every redeploy never clobbers an admin's edits (disabled
        # models, custom upstream ids, reordering). Use --force to reset to defaults.
        if not force:
            count = await session.scalar(select(func.count()).select_from(AIModel))
            if count:
                print(f"AI catalog has {count} models — skipping (use --force to reset).")
                return
        for order, tm in enumerate(TEXT_MODELS, start=1):
            upstream = _UPSTREAM.get(tm.key, tm.key)
            m = await session.get(AIModel, tm.key)
            if m is None:
                m = AIModel(key=tm.key)
                session.add(m)
            m.title = tm.name
            m.upstream_model = upstream
            m.modality = "text"
            m.premium = tm.premium
            m.cost = tm.cost
            m.enabled = True
            m.sort_order = order
        await session.commit()
    print(f"✅ Seeded {len(TEXT_MODELS)} AI models.")


if __name__ == "__main__":
    asyncio.run(main(force="--force" in sys.argv))
