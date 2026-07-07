"""Approximate ₽ fiat hint shown next to Stars prices in purchase keyboards."""
from __future__ import annotations

from bot.keyboards.inline import fiat_hint, premium_durations
from core.config import settings
from core.i18n import Translator


def test_fiat_hint_renders_rounded_rubles():
    expected = round(600 * settings.stars_to_rub)
    out = fiat_hint(600)
    assert "₽" in out
    assert str(expected) in out


def test_fiat_hint_safe_when_rate_zero(monkeypatch):
    monkeypatch.setattr(settings, "stars_to_rub", 0.0)
    assert fiat_hint(600) == ""


def test_fiat_hint_safe_for_zero_stars():
    assert fiat_hint(0) == ""


def test_premium_durations_button_shows_ruble():
    _ = Translator("ru")
    kb = premium_durations(_, "premium", prices={1: 600, 3: 1500})
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("₽" in t and "⭐" in t for t in texts)
