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


# Web-search-capable models for the /s picker (seeded with search=True). Upstream ids
# are the REAL search variants — Perplexity Sonar routes via the Perplexity key; the
# OpenAI *-search-preview + OpenRouter ":online" variants route through the normal
# account pool (OmniRoute/OpenRouter/OpenAI). The admin can enable/disable, rename,
# fix the upstream id, or add more in the AI-routing panel (tick «Поиск (/s)»).
# (key, title, upstream_model, premium)
SEARCH_MODELS: list[tuple[str, str, str, bool]] = [
    ("search_perplexity_sonar", "Perplexity Sonar", "perplexity/sonar", False),
    ("search_perplexity_sonar_pro", "Perplexity Sonar Pro", "perplexity/sonar-pro", True),
    ("search_gpt_web", "GPT Поиск", "openai/gpt-4o-search-preview", True),
    ("search_gemini_web", "Gemini Поиск", "google/gemini-1.5-flash:online", False),
]


async def seed_search_models(session) -> int:
    """Idempotent add-if-missing of the /s search models. Runs on every seed (even a
    non-empty catalog) so the search picker has options out of the box; NEVER touches
    an existing row, so admin edits (disable/rename/upstream) are preserved."""
    added = 0
    for order, (key, title, upstream, premium) in enumerate(SEARCH_MODELS, start=1):
        if await session.get(AIModel, key) is not None:
            continue
        session.add(AIModel(
            key=key, title=title, upstream_model=upstream, modality="text",
            premium=premium, search=True, cost=1, enabled=True, sort_order=1000 + order,
        ))
        added += 1
    if added:
        await session.commit()
    return added


async def main(force: bool = False) -> None:
    async with SessionFactory() as session:
        # Safe to wire into the deploy: only seed an EMPTY catalog (first boot), so
        # re-running on every redeploy never clobbers an admin's edits (disabled
        # models, custom upstream ids, reordering). Use --force to reset to defaults.
        count = await session.scalar(select(func.count()).select_from(AIModel))
        if force or not count:
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
            print(f"✅ Seeded {len(TEXT_MODELS)} text AI models.")
        else:
            print(f"AI catalog has {count} models — skipping text seed (use --force to reset).")
        # Always ensure the /s search models exist (idempotent, admin-safe).
        n = await seed_search_models(session)
        print(f"✅ Search models: {n} added ({len(SEARCH_MODELS)} total defined).")


if __name__ == "__main__":
    asyncio.run(main(force="--force" in sys.argv))
