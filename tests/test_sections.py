"""Menu sections (full-product launch): every section ships ON; any section can be
toggled OFF with its own editable "coming soon" text, all via the live
business_config. Guards the pricing.section_state() merge the bot handlers gate on."""
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


async def test_all_sections_default_on_with_soon_text():
    # Full product: every section ships ON, and each still carries an editable
    # "coming soon" message used when the admin turns it OFF.
    async with SessionFactory() as s:
        for name in ("images", "video", "music", "search", "documents"):
            sec = await pricing.section_state(s, name)
            assert sec["enabled"] is True
            assert sec["soon"]  # non-empty default text (shown only when toggled off)


async def test_override_enables_and_customises():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"sections": {
            "video": {"enabled": True},
            "music": {"enabled": False, "soon": "музыка будет в марте"},
        }})
    async with SessionFactory() as s:
        assert (await pricing.section_state(s, "video"))["enabled"] is True
        music = await pricing.section_state(s, "music")
        assert music["enabled"] is False
        assert music["soon"] == "музыка будет в марте"
        # Untouched section keeps its default (on).
        assert (await pricing.section_state(s, "images"))["enabled"] is True


async def test_unknown_section_defaults_enabled():
    # A section without a config entry must not be accidentally hidden.
    async with SessionFactory() as s:
        assert (await pricing.section_state(s, "totally_new"))["enabled"] is True


async def test_pack_follows_its_section():
    # A pack is only sold when its media section is on (default on → sold;
    # turning the section off hides the pack too).
    async with SessionFactory() as s:
        assert (await pricing.pack_section_state(s, "video_pack"))["enabled"] is True
        await pricing.set_config(s, {"sections": {"video": {"enabled": False}}})
    async with SessionFactory() as s:
        assert (await pricing.pack_section_state(s, "video_pack"))["enabled"] is False
        # Unknown pack is never section-gated.
        assert (await pricing.pack_section_state(s, "mystery_pack"))["enabled"] is True
