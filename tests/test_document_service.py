"""Documents service config (ТЗ §5/§1): admin-editable cost + on/off feature flag."""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base
from core.services import feature_flags, pricing


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await pricing.redis_client.delete(pricing._CACHE_KEY)
        await feature_flags.redis_client.delete(feature_flags._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield


async def test_document_cost_default_then_override():
    async with SessionFactory() as s:
        assert await pricing.document_cost(s) == 3          # default
        await pricing.set_config(s, {"documents": {"cost": 7}})
        assert await pricing.document_cost(s) == 7          # admin override
        # never drops below 1 even if misconfigured
        await pricing.set_config(s, {"documents": {"cost": 0}})
        assert await pricing.document_cost(s) == 1


async def test_documents_flag_default_on_and_toggleable():
    async with SessionFactory() as s:
        assert "documents" in feature_flags.default_flags()
        assert await feature_flags.is_enabled(s, "documents") is True
        await feature_flags.set_flag(s, "documents", False)
        assert await feature_flags.is_enabled(s, "documents") is False


async def test_search_system_prompt_default_then_override():
    async with SessionFactory() as s:
        assert "интернет" in (await pricing.search_system_prompt(s)).lower()  # default
        await pricing.set_config(s, {"search": {"system_prompt": "Custom search prompt."}})
        assert await pricing.search_system_prompt(s) == "Custom search prompt."
        # blank falls back to the default, never an empty system prompt
        await pricing.set_config(s, {"search": {"system_prompt": ""}})
        assert "интернет" in (await pricing.search_system_prompt(s)).lower()
