"""The shared option resolver (core.services.service_config.effective_options) and
the Mini App effect card both honour the admin's service_options + hide with the
SAME money-guard as the bot keyboards (ТЗ §5/§8). One source of truth → the bot
config keyboard and the Mini App create screen show identical options.
"""
from __future__ import annotations

from api.routers.miniapp import _model_card
from core.ai_router.image_specs import PHOTO_SPECS
from core.ai_router.video_specs import VIDEO_SPECS
from core.services.service_config import effective_options


# ---- effective_options: the money-guard ------------------------------------
def test_cost_field_narrowed_and_unpriced_dropped():
    spec = PHOTO_SPECS["nano_banana"]            # qualities drive _nano_cost
    eff = effective_options(spec, {"qualities": ["1k", "8k", "4k"]})
    assert eff.qualities == ["1k", "4k"]          # 8k is unpriced → dropped


def test_all_unknown_cost_values_fall_back_to_spec():
    spec = PHOTO_SPECS["nano_banana"]
    eff = effective_options(spec, {"qualities": ["8k", "16k"]})
    assert eff.qualities == list(spec.qualities)  # guard never empties the menu


def test_ratios_are_free_to_extend():
    spec = PHOTO_SPECS["gpt_image2"]              # ratios are cost-neutral
    eff = effective_options(spec, {"ratios": ["1:1", "21:9"]})
    assert eff.ratios == ["1:1", "21:9"]          # brand-new 21:9 kept


def test_video_durations_guarded():
    spec = VIDEO_SPECS["kling_ai"]                # durations drive _kling_cost
    eff = effective_options(spec, {"durations": [5, 99]})
    assert eff.durations == [5]                   # 99 unpriced → dropped


def test_hide_is_exposed():
    spec = VIDEO_SPECS["kling_ai"]
    eff = effective_options(spec, {"hide": ["fourk"]})
    assert "fourk" in eff.hide


# ---- Mini App effect card mirrors the same rules ---------------------------
def test_card_default_shows_full_spec():
    card = _model_card("video", "kling_ai")
    assert card["fourk"] is True
    assert card["audio"] is True
    assert card["durations"] == list(VIDEO_SPECS["kling_ai"].durations)


def test_card_applies_admin_narrowing_and_hide():
    card = _model_card("video", "kling_ai", {"durations": [5, 99], "hide": ["fourk"]})
    assert card["durations"] == [5]               # narrowed + unpriced dropped
    assert "fourk" not in card                    # toggle hidden by admin
    assert card["audio"] is True                  # untouched toggle stays


def test_card_quality_unpriced_dropped():
    card = _model_card("photo", "nano_banana", {"qualities": ["1k", "8k"]})
    assert card["qualities"] == ["1k"]            # 8k dropped, money-safe
