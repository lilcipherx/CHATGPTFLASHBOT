"""Per-service generation option BUTTONS are admin-editable (ТЗ §5/§8): the config
sub-menu shows the admin's option lists when set, else the code spec's defaults.
Only the buttons change — costs/flow stay in code."""
from __future__ import annotations

import pytest_asyncio

from bot.keyboards.photo_config import service_config_kb
from bot.keyboards.video_config import video_config_kb
from core.ai_router.image_specs import PHOTO_SPECS
from core.ai_router.video_specs import VIDEO_SPECS
from core.db import SessionFactory, engine
from core.i18n import Translator
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


def _btn_data(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


async def test_service_options_empty_by_default():
    async with SessionFactory() as s:
        assert await pricing.service_options(s) == {}


async def test_admin_override_sanitised():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"service_options": {
            "gpt_image2": {"ratios": ["1:1", "16:9", "  "], "counts": [1, 2, "x", 3]},
            "bad": {"ratios": "notalist"},   # malformed → dropped
        }})
    async with SessionFactory() as s:
        opts = await pricing.service_options(s)
    assert opts["gpt_image2"]["ratios"] == ["1:1", "16:9"]   # blank trimmed out
    assert opts["gpt_image2"]["counts"] == [1, 2, 3]          # non-int dropped
    assert "bad" not in opts


async def test_keyboard_uses_override_ratios():
    _ = Translator("ru")
    spec = PHOTO_SPECS["gpt_image2"]
    # default spec offers 5 ratios; override narrows to 2.
    override = {"ratios": ["1:1", "16:9"]}
    data = _btn_data(service_config_kb(_, spec, dict(spec.default), None, override))
    ratio_btns = [d for d in data if d.startswith("pcfg:ratio:")]
    assert ratio_btns == ["pcfg:ratio:1:1", "pcfg:ratio:16:9"]


async def test_keyboard_falls_back_to_spec_when_no_override():
    _ = Translator("ru")
    spec = PHOTO_SPECS["gpt_image2"]
    data = _btn_data(service_config_kb(_, spec, dict(spec.default)))
    ratio_btns = [d for d in data if d.startswith("pcfg:ratio:")]
    assert len(ratio_btns) == len(spec.ratios)  # all code-default ratios shown


async def test_cost_field_unknown_value_is_dropped():
    # Quality drives the per-image cost (_nano_cost); an admin can't add an unpriced
    # value (e.g. "8k") that would undercharge — unknown values are filtered out.
    _ = Translator("ru")
    spec = PHOTO_SPECS["nano_banana"]
    override = {"qualities": ["1k", "8k", "4k"]}  # 8k is not priced in code
    data = _btn_data(service_config_kb(_, spec, dict(spec.default), None, override))
    qual_btns = [d for d in data if d.startswith("pcfg:quality:")]
    assert qual_btns == ["pcfg:quality:1k", "pcfg:quality:4k"]  # 8k dropped


async def test_ratios_are_free_to_add():
    # Ratios don't affect cost, so an admin may add a brand-new one.
    _ = Translator("ru")
    spec = PHOTO_SPECS["gpt_image2"]
    override = {"ratios": ["1:1", "21:9"]}  # 21:9 not in the spec defaults
    data = _btn_data(service_config_kb(_, spec, dict(spec.default), None, override))
    ratio_btns = [d for d in data if d.startswith("pcfg:ratio:")]
    assert ratio_btns == ["pcfg:ratio:1:1", "pcfg:ratio:21:9"]


async def test_hide_toggle_removes_button():
    # Admin hiding the 4K toggle on Kling removes its button from the keyboard.
    _ = Translator("ru")
    spec = VIDEO_SPECS["kling_ai"]
    shown = _btn_data(video_config_kb(_, spec, dict(spec.default)))
    assert "vcfg:fourk:toggle" in shown
    hidden = _btn_data(video_config_kb(_, spec, dict(spec.default), None, {"hide": ["fourk"]}))
    assert "vcfg:fourk:toggle" not in hidden
    assert "vcfg:audio:toggle" in hidden  # other toggles untouched


async def test_hide_sanitised_to_known_toggles():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"service_options": {
            "kling_ai": {"hide": ["fourk", "bogus"]},  # bogus is not a real toggle
        }})
    async with SessionFactory() as s:
        opts = await pricing.service_options(s)
    assert opts["kling_ai"]["hide"] == ["fourk"]
