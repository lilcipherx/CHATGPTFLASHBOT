"""Image service specs, cost functions, pack-field mapping (pure logic)."""
from __future__ import annotations

import pytest

from core.ai_router.image_specs import PHOTO_SPECS
from core.constants import PACK_PRICES
from core.services import packs


def test_specs_present():
    assert set(PHOTO_SPECS) == {
        "gpt_image2", "nano_banana", "seedream", "midjourney", "flux2", "recraft"
    }


def test_weekly_vs_pack_budget():
    # GPT Image 2 + Nano Banana draw on weekly quota, NOT the image pack (§10.2)
    assert PHOTO_SPECS["gpt_image2"].pack is None
    assert PHOTO_SPECS["nano_banana"].pack is None
    assert PHOTO_SPECS["seedream"].pack == "image"
    assert PHOTO_SPECS["flux2"].pack == "image"


def test_nano_cost_by_quality():
    cost = PHOTO_SPECS["nano_banana"].cost
    assert cost({"quality": "1k"}) == 2
    assert cost({"quality": "2k"}) == 3
    assert cost({"quality": "4k"}) == 4


def test_flux_variant_cost():
    cost = PHOTO_SPECS["flux2"].cost
    assert cost({"model": "flux2"}) == 1
    assert cost({"model": "flux2_pro"}) == 1
    assert cost({"model": "flux2_flex"}) == 2
    assert cost({"model": "flux2_max"}) == 2


def test_pack_field_mapping():
    assert packs.PACK_FIELD == {
        "image": "image_credits",
        "video": "video_credits",
        "music": "music_credits",
    }
    with pytest.raises(ValueError):
        packs._field("bogus")


def test_pack_pricing_intact():
    assert PACK_PRICES["image_pack"][200] == 800
    assert PACK_PRICES["video_pack"][50] == 2000
