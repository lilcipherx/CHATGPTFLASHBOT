"""Premium models carry a 💎 badge in the picker (ТЗ §3, GRILL_BACKLOG Q8)."""
from __future__ import annotations

from bot.keyboards.inline import model_keyboard
from core.constants import TEXT_MODELS
from core.i18n import Translator


def _texts(kb):
    return [b.text for row in kb.inline_keyboard for b in row]


def test_db_models_badge_premium_keys():
    _ = Translator("ru")
    items = [("free1", "Free One"), ("paid1", "Paid One")]
    kb = model_keyboard(_, "free1", items, premium_keys={"paid1"})
    texts = _texts(kb)
    assert any("Paid One 💎" in t for t in texts)
    assert not any("Free One 💎" in t for t in texts)   # free model is unbadged


def test_static_catalog_derives_premium_badge():
    _ = Translator("ru")
    kb = model_keyboard(_, "none")  # static TEXT_MODELS fallback, premium_keys derived
    texts = _texts(kb)
    premium_names = {m.name for m in TEXT_MODELS if m.premium}
    if premium_names:  # only assert when the static catalog actually has a premium model
        assert any("💎" in t for t in texts)
