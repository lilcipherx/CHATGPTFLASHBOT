"""Regression: an admin can extend the cost-neutral `ratios` list without limit
(core/services/service_config.py treats ratios as 'free to extend'). The config
keyboards must wrap buttons so no row exceeds Telegram's 8-per-row cap — aiogram's
adjust() raises ValueError above 8, which would crash the whole config menu."""
from __future__ import annotations

from bot.keyboards.photo_config import service_config_kb
from bot.keyboards.video_config import video_config_kb
from core.ai_router.image_specs import PHOTO_SPECS
from core.ai_router.video_specs import VIDEO_SPECS
from core.i18n import Translator


def _rows(markup) -> list[int]:
    return [len(r) for r in markup.inline_keyboard]


def test_video_config_wraps_many_ratios():
    _ = Translator("ru")
    spec = next(iter(VIDEO_SPECS.values()))
    override = {"ratios": [f"{i}:1" for i in range(1, 13)]}  # 12 admin ratios
    markup = video_config_kb(_, spec, dict(spec.default), {}, override)
    assert max(_rows(markup)) <= 8  # no row exceeds Telegram's cap
    # all 12 ratio buttons are present across the wrapped rows
    labels = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert sum(1 for c in labels if c.startswith("vcfg:ratio:")) == 12


def test_photo_config_wraps_many_ratios():
    _ = Translator("ru")
    spec = next(iter(PHOTO_SPECS.values()))
    override = {"ratios": [f"{i}:1" for i in range(1, 13)]}
    markup = service_config_kb(_, spec, dict(spec.default), {}, override)
    assert max(_rows(markup)) <= 8
    labels = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert sum(1 for c in labels if c.startswith("pcfg:ratio:")) == 12


def test_default_specs_render_without_error():
    """Every real spec's default config keyboard builds (no row >8)."""
    _ = Translator("ru")
    for spec in VIDEO_SPECS.values():
        assert max(_rows(video_config_kb(_, spec, dict(spec.default), {}, None))) <= 8
    for spec in PHOTO_SPECS.values():
        assert max(_rows(service_config_kb(_, spec, dict(spec.default), {}, None))) <= 8
