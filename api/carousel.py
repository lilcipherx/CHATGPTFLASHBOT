"""Mini App carousel render-behaviour config (animation/autoplay/loop/…).

The admin writes it (``api.admin.banners``), the public Mini App reads it back
(``api.routers.miniapp``). Kept in a neutral module so the public and admin routers
don't import each other. Defaults keep the current look."""
from __future__ import annotations

ANIMATIONS = {"slide", "fade"}
BEHAVIOR_DEFAULTS: dict = {
    "animation": "slide",          # slide | fade
    "speed_ms": 400,               # transition duration
    "autoplay": True,
    "pause_on_interaction": True,
    "loop": True,
    "show_indicators": True,
    "show_arrows": False,
    "manual_swipe": True,
}
_BEHAVIOR_BOOLS = (
    "autoplay", "pause_on_interaction", "loop",
    "show_indicators", "show_arrows", "manual_swipe",
)


def _sanitize_behavior(raw: dict | None) -> dict:
    beh = dict(BEHAVIOR_DEFAULTS)
    raw = raw or {}
    if raw.get("animation") in ANIMATIONS:
        beh["animation"] = raw["animation"]
    try:
        beh["speed_ms"] = max(100, min(2000, int(raw.get("speed_ms", beh["speed_ms"]))))
    except (TypeError, ValueError) as exc:
        import structlog
        structlog.get_logger().warning('api.carousel._sanitize_behavior_failed', error=str(exc))
        # FIX: AUDIT12-L1 - was silent except: pass
    for k in _BEHAVIOR_BOOLS:
        if k in raw:
            beh[k] = bool(raw[k])
    return beh
