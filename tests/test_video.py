"""Video service specs + cost functions (§22) and adapter routing."""
from __future__ import annotations

from core.ai_router.video_adapters import provider_for
from core.ai_router.video_specs import VIDEO_SPECS


def test_all_video_services_present():
    assert set(VIDEO_SPECS) == {
        "seedance", "veo", "grok", "kling_ai", "hailuo", "pika", "mj_video"
    }


def test_mj_video_charges_image_pack():
    # Midjourney Video draws on the image pack, not the video pack (§26C)
    assert VIDEO_SPECS["mj_video"].pack == "image"
    assert VIDEO_SPECS["seedance"].pack == "video"


def test_kling_cost_by_duration_and_4k():
    cost = VIDEO_SPECS["kling_ai"].cost
    assert cost({"duration": 5}) == 1
    assert cost({"duration": 10}) == 2
    assert cost({"duration": 15}) == 3
    assert cost({"duration": 15, "fourk": True}) == 6  # 4K ×2


def test_grok_edit_costs_two():
    cost = VIDEO_SPECS["grok"].cost
    assert cost({"mode": "create"}) == 1
    assert cost({"mode": "edit"}) == 2


def test_pika_cost_matrix():
    cost = VIDEO_SPECS["pika"].cost
    assert cost({"duration": 5, "res": "720p"}) == 1
    assert cost({"duration": 5, "res": "1080p"}) == 2
    assert cost({"duration": 10, "res": "720p"}) == 2
    assert cost({"duration": 10, "res": "1080p"}) == 3


def test_kling_powers_three_services():
    # Kling AI / Effects / Motion all route to the Kling provider (§20)
    assert provider_for("kling_ai").name == "kling"
    assert provider_for("kling_effects").name == "kling"
    assert provider_for("kling_motion").name == "kling"


def test_unavailable_without_key():
    # no API keys configured in test env -> all providers unavailable
    assert provider_for("veo").is_available() is False
