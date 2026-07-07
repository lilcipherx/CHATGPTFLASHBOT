"""Service "Инструкция" links are admin-editable and empty by default — no
third-party links ship, and only safe http(s) URLs ever render a button."""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base
from core.services import pricing


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield


async def test_doc_links_empty_by_default():
    async with SessionFactory() as s:
        assert await pricing.doc_links(s) == {}


async def test_doc_links_admin_set_and_sanitised():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"doc_links": {
            "banana": "https://my.site/banana",
            "veo": "  http://my.site/veo  ",   # trimmed, http allowed
            "gpt_images": "javascript:alert(1)",  # unsafe scheme → dropped
            "midjourney": "",                      # empty → dropped
        }})
    async with SessionFactory() as s:
        links = await pricing.doc_links(s)
    assert links["banana"] == "https://my.site/banana"
    assert links["veo"] == "http://my.site/veo"
    assert "gpt_images" not in links
    assert "midjourney" not in links
