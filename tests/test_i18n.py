"""i18n completeness for key screens across all 8 locales + label aggregation."""
from __future__ import annotations

from core.constants import SUPPORTED_LOCALES
from core.i18n import Translator, all_labels, t


def test_every_locale_has_all_ru_keys():
    """No locale may silently fall back to Russian — full coverage required."""
    import importlib

    from core.i18n.locales import ru as ru_mod

    ru_keys = set(ru_mod.MESSAGES)
    for loc in SUPPORTED_LOCALES:
        if loc == "ru":
            continue
        mod = importlib.import_module(f"core.i18n.locales.{loc}")
        missing = ru_keys - set(getattr(mod, "MESSAGES", {}))
        assert not missing, f"{loc} missing keys: {sorted(missing)}"


def test_all_locales_have_key_screens():
    assert len(SUPPORTED_LOCALES) == 8
    for loc in SUPPORTED_LOCALES:
        # start.welcome translated (or RU fallback) — never the raw key
        assert t("start.welcome", loc, support="@x") != "start.welcome"


def test_missing_key_falls_back_to_ru():
    # 'help' (long body) defined in RU -> Chinese falls back, not echoes the key
    assert t("help", "zh", support="@x").startswith("📚")


def test_no_placeholder_mismatch_across_locales():
    """Every locale must render the dynamic screens with the exact kwargs the
    handlers pass — guards against KeyError crashes on language switch."""
    account_kw = dict(
        used=5, limit=100, credits=0, sub="x", model_name="Gemini", image=0, video=0,
        music=0, support="@lilcipher",
    )
    for loc in SUPPORTED_LOCALES:
        assert "{" not in t("account", loc, **account_kw)  # no leftover placeholder
        assert t("start.welcome", loc, support="@lilcipher")
        assert t("premium", loc, support="@lilcipher", p_premium=600,
                 p_premium_x2=900, p_image_from=250, p_video_from=150,
                 p_music_from=250)
        assert t("help", loc, support="@lilcipher")
        assert t("quota.exceeded.free", loc, used=1, limit=100)
        assert t("model.selected", loc, name="GPT")
        # templated purchase / generation keys must render with their kwargs
        assert t("pack.choose", loc, name="X")
        assert t("pay.sub_invoice_desc", loc, title="X")
        assert t("pay.pack_invoice_desc", loc, title="X")
        assert t("pay.sub_activated", loc, title="X")
        assert t("pay.pack_added", loc, qty=50, unit="g", pack="P")
        assert t("pay.link_btn", loc, title="X")
        assert t("gen.photo_started", loc, name="X")
        assert t("avatar.info", loc, price=200)
        assert t("avatar.buy_btn", loc, price=200)
        assert t("music.prompt", loc, name="Suno")
        assert t("kling.effect_selected", loc, name="X")
        assert t("kling.motion_selected", loc, name="X")
        for m in (1, 3, 6, 12):
            assert t(f"duration.{m}", loc)


def test_every_templated_key_renders_in_all_locales():
    """Auto-discovers every RU key containing {placeholders} and renders it in
    all locales with dummy kwargs — catches any placeholder typo/mismatch."""
    import re

    from core.i18n.locales import ru as ru_mod

    ph = re.compile(r"\{(\w+)\}")
    for key, val in ru_mod.MESSAGES.items():
        names = set(ph.findall(val))
        if not names:
            continue
        kwargs = {n: "1" for n in names}
        for loc in SUPPORTED_LOCALES:
            out = t(key, loc, **kwargs)  # must not raise (KeyError on bad placeholder)
            assert "{" not in out, f"{loc}/{key} leftover placeholder: {out!r}"


def test_all_labels_covers_locales():
    labels = all_labels("btn.account")
    # Reply-keyboard buttons carry a leading emoji (owner-specified layout); the
    # text after the emoji must still be the localized label.
    assert "👤 Мой профиль" in labels    # RU
    assert "👤 My profile" in labels     # EN
    assert "👤 我的资料" in labels         # ZH
    # each locale renders its own button via the translator
    assert Translator("fr")("btn.account") == "👤 Mon profil"
    assert Translator("es")("btn.images") == "🎨 Crear imagen"
