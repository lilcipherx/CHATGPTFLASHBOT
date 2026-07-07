"""Sale visibility in buy keyboards (ТЗ §4): when a sale is active the buttons show
the pre-sale price → discounted price + the percent, and a banner with a countdown
is prepended to the menu. Off-sale the labels stay unchanged."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bot.keyboards.inline import (
    pack_qty_keyboard,
    premium_durations,
    price_tag,
    promo_banner,
    sale_banner,
)
from core.i18n import Translator


def test_price_tag_no_sale_shows_single_price():
    out = price_tag(600, 0)
    assert "600 ⭐" in out
    assert "→" not in out and "−" not in out


def test_price_tag_with_sale_shows_original_and_discounted():
    # 600 -20% = 480, with the same rounding the charge path uses
    out = price_tag(600, 20)
    assert "600→480 ⭐" in out
    assert "−20%" in out


def test_premium_durations_buttons_show_sale_arrow():
    _ = Translator("ru")
    kb = premium_durations(_, "premium", prices={1: 600, 3: 1500}, sale_pct=50)
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert any("600→300 ⭐" in t and "−50%" in t for t in texts)
    assert any("1500→750 ⭐" in t for t in texts)


def test_pack_qty_buttons_show_sale_arrow():
    _ = Translator("ru")
    kb = pack_qty_keyboard(_, "image_pack", prices={50: 250}, sale_pct=50)
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert any("250→125 ⭐" in t and "−50%" in t for t in texts)


def test_sale_banner_empty_when_inactive():
    _ = Translator("ru")
    assert sale_banner(_, {"active": False, "percent": 0}) == ""


def test_sale_banner_shows_percent_and_countdown():
    _ = Translator("ru")
    until = (datetime.now(UTC) + timedelta(hours=3, minutes=30)).isoformat()
    out = sale_banner(_, {"active": True, "percent": 25, "until": until})
    assert "−25%" in out
    assert "3ч" in out  # countdown rendered (hours+minutes form)


def test_sale_banner_no_countdown_without_until():
    _ = Translator("ru")
    out = sale_banner(_, {"active": True, "percent": 25, "until": None})
    assert "−25%" in out
    assert "⏳" not in out


def test_promo_banner_shows_applied_percent():
    _ = Translator("ru")
    assert "−15%" in promo_banner(_, 15)
    assert promo_banner(_, 0) == ""
