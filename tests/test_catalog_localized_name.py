"""Catalog rows expose localized_name(locale): the locale's translation, else
English, else the canonical Russian name (so non-RU users never see raw Russian)."""
from __future__ import annotations

from core.models.catalog import (
    KlingEffectTemplate,
    KlingMotionTemplate,
    MiniAppPhotoEffect,
)


def test_ru_returns_canonical_name_ru():
    t = KlingEffectTemplate(name_ru="Поцелуй", name_i18n={"en": "Kiss"})
    assert t.localized_name("ru") == "Поцелуй"


def test_known_locale_uses_translation():
    t = KlingMotionTemplate(name_ru="Бег", name_i18n={"en": "Running", "es": "Correr"})
    assert t.localized_name("en") == "Running"
    assert t.localized_name("es") == "Correr"


def test_unknown_locale_falls_back_to_english():
    t = KlingEffectTemplate(name_ru="Ракета", name_i18n={"en": "Rocket"})
    # no 'fr' entry → English, not raw Russian
    assert t.localized_name("fr") == "Rocket"
    assert t.localized_name("ar") == "Rocket"


def test_no_i18n_falls_back_to_name_ru():
    t = KlingEffectTemplate(name_ru="Только рус", name_i18n={})
    assert t.localized_name("es") == "Только рус"
    # also robust when the column is None rather than {}
    t2 = MiniAppPhotoEffect(name_ru="Glamour Portrait", name_i18n=None)
    assert t2.localized_name("zh") == "Glamour Portrait"
