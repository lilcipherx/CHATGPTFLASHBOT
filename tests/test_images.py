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


# ---- decompression-bomb (pixel-bomb) guard --------------------------------
def _png_bytes(size=(8, 8)):
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, format="PNG")
    return buf.getvalue()


def test_validate_image_rejects_oversized_dimensions(monkeypatch):
    """A file whose DECLARED dimensions exceed the ceiling is rejected (413) before any
    pixel decode — the decompression-bomb guard. Threshold patched low so the test never
    has to allocate a real multi-gigapixel buffer."""
    from fastapi import HTTPException

    from api import images

    monkeypatch.setattr(images, "_MAX_IMAGE_PIXELS", 16)  # 8x8 = 64 px > 16 → reject
    with pytest.raises(HTTPException) as exc:
        images._validate_image(_png_bytes((8, 8)))
    assert exc.value.status_code == 413


def test_validate_image_accepts_within_dimensions(monkeypatch):
    from api import images

    monkeypatch.setattr(images, "_MAX_IMAGE_PIXELS", 1_000_000)
    assert images._validate_image(_png_bytes((8, 8))) == ".png"


def test_normalize_image_rejects_pixel_bomb(monkeypatch):
    """The transcode path (non jpg/png/webp) must also bail before im.load()."""
    import io

    from PIL import Image

    from api import images

    gif = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(gif, format="GIF")
    monkeypatch.setattr(images, "_MAX_IMAGE_PIXELS", 16)
    assert images._normalize_image(gif.getvalue()) is None
