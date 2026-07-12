"""Unit tests for the pack-purchase callback flow (bot/handlers/packs_buy.py).

Covers the guard rails without a live DB (services monkeypatched): unknown pack,
disabled section (defence-in-depth on BOTH the menu and the pay step), malformed
callback_data, a missing price, and the Stars-invoice happy path. Mirrors the
duck-typed fake-callback style used in tests/test_voice_output.py.
"""
from __future__ import annotations

import pytest

from bot.handlers import packs_buy
from core.i18n import Translator


class _FakeMsg:
    def __init__(self) -> None:
        self.chat = type("C", (), {"id": 1})()
        self.answers: list = []
        self.edits: list = []
        self.invoices: list = []

    async def answer(self, text=None, **k):
        self.answers.append(text)
        return None

    async def edit_text(self, text=None, **k):
        self.edits.append(text)
        return None

    async def answer_invoice(self, **k):
        self.invoices.append(k)
        return None


class _FakeCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.message = _FakeMsg()
        self.answered = False

    async def answer(self, *a, **k):
        self.answered = True


def _user():
    return type("U", (), {"user_id": 42, "is_premium": False})()


@pytest.mark.asyncio
async def test_cb_pack_unknown_pack_is_ignored():
    """A forged pack key not in PACK_PRICES is acknowledged but offers nothing."""
    cb = _FakeCallback("pack:not_a_real_pack")
    await packs_buy.cb_pack(cb, session=object(), user=_user(), _=Translator("ru"))
    assert cb.answered
    assert cb.message.answers == []


@pytest.mark.asyncio
async def test_cb_pack_disabled_section_shows_soon(monkeypatch):
    """A pack whose section the admin turned off shows its 'coming soon' text, not a menu."""
    async def _section(_s, _p):
        return {"enabled": False, "soon": "soon-text"}

    monkeypatch.setattr(packs_buy.pricing, "pack_section_state", _section)
    cb = _FakeCallback("pack:image_pack")
    await packs_buy.cb_pack(cb, session=object(), user=_user(), _=Translator("ru"))
    assert cb.answered
    assert "soon-text" in cb.message.answers


@pytest.mark.asyncio
async def test_cb_pack_qty_malformed_payload_is_ignored():
    """packqty:<pack>:<non-int> must not raise — it is silently acknowledged."""
    cb = _FakeCallback("packqty:image_pack:notanint")
    await packs_buy.cb_pack_qty(cb, _=Translator("ru"))
    assert cb.answered
    assert cb.message.edits == []


@pytest.mark.asyncio
async def test_cb_pack_pay_disabled_section_blocks_charge(monkeypatch):
    """Defence in depth: a stale pay button for a now-disabled section never charges."""
    async def _section(_s, _p):
        return {"enabled": False, "soon": "x"}

    monkeypatch.setattr(packs_buy.pricing, "pack_section_state", _section)
    cb = _FakeCallback("packpay:stars:image_pack:10")
    await packs_buy.cb_pack_pay(cb, session=object(), user=_user(), _=Translator("ru"))
    assert cb.answered
    assert cb.message.invoices == []


@pytest.mark.asyncio
async def test_cb_pack_pay_missing_price_is_ignored(monkeypatch):
    """A pack/qty with no configured price is acknowledged without an invoice."""
    async def _section(_s, _p):
        return {"enabled": True}

    async def _price(_s, _p, _q, **k):
        return None

    monkeypatch.setattr(packs_buy.pricing, "pack_section_state", _section)
    monkeypatch.setattr(packs_buy.pricing, "pack_price", _price)
    cb = _FakeCallback("packpay:stars:image_pack:10")
    await packs_buy.cb_pack_pay(cb, session=object(), user=_user(), _=Translator("ru"))
    assert cb.answered
    assert cb.message.invoices == []


@pytest.mark.asyncio
async def test_cb_pack_pay_stars_creates_invoice(monkeypatch):
    """The Stars path builds an XTR invoice with the pack:<pack>:<qty> payload."""
    async def _section(_s, _p):
        return {"enabled": True}

    async def _price(_s, _p, _q, **k):
        return 100

    async def _pct(_s, _u):
        return 0

    async def _record(_s, *a, **k):
        return None

    monkeypatch.setattr(packs_buy.pricing, "pack_section_state", _section)
    monkeypatch.setattr(packs_buy.pricing, "pack_price", _price)
    monkeypatch.setattr(packs_buy.promos, "checkout_percent", _pct)
    import core.services.checkout as _checkout
    monkeypatch.setattr(_checkout, "record_intent", _record)

    cb = _FakeCallback("packpay:stars:image_pack:10")
    await packs_buy.cb_pack_pay(cb, session=object(), user=_user(), _=Translator("ru"))
    assert cb.answered
    assert len(cb.message.invoices) == 1
    inv = cb.message.invoices[0]
    assert inv["payload"] == "pack:image_pack:10"
    assert inv["currency"] == "XTR"
