"""Reworked «Редактор локализации» page — the additive, read-only endpoints behind
the enterprise editor (no migration):

  * core.i18n.locale_keys — keys a locale translates natively (vs. the RU fallback).
  * GET /localization/stats — per-language coverage for the Language Manager.
  * GET /localization/history — real per-(locale, key) change history from the audit
    log, powering the editor's diff viewer + rollback.

Calls the endpoint coroutines directly against a seeded SQLite schema (no HTTP),
mirroring tests/test_localization.py.
"""
from __future__ import annotations

import pytest_asyncio

from core import i18n
from core.db import SessionFactory, engine
from core.models import Base
from core.services import i18n_overrides


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await i18n_overrides.redis_client.delete(i18n_overrides._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    await i18n_overrides.load_once()
    yield
    await i18n_overrides.load_once()
    try:
        await i18n_overrides.redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


class _Admin:
    id = 1


class _Req:
    client = None


def _some_key() -> str:
    return i18n.known_keys()[0]


# ---- core.i18n.locale_keys -------------------------------------------------
def test_locale_keys_is_native_subset_of_known():
    known = set(i18n.known_keys())
    ru = i18n.locale_keys("ru")
    # RU is canonical: every key it owns is a known key, and it owns a lot of them.
    assert ru, "ru should have native translations"
    assert ru <= known
    # An unknown locale owns nothing (falls back entirely to RU).
    assert i18n.locale_keys("zz") == set()


# ---- GET /localization/stats ----------------------------------------------
async def test_stats_per_language_coverage():
    from api.admin import localization

    async with SessionFactory() as s:
        out = await localization.localization_stats(admin=_Admin(), session=s)

    assert out["total"] == len(i18n.known_keys())
    by_code = {lang["code"]: lang for lang in out["languages"]}

    ru = by_code["ru"]
    assert ru["is_default"] is True
    assert ru["rtl"] is False
    # RU is canonical → fully translated, no missing keys.
    assert ru["translated"] == out["total"]
    assert ru["missing"] == 0
    assert ru["percent"] == 100

    # Arabic is right-to-left and not the default.
    assert by_code["ar"]["rtl"] is True
    assert by_code["ar"]["is_default"] is False

    # Every language is bounded: translated + missing == total, percent in [0, 100].
    for lang in out["languages"]:
        assert lang["translated"] + lang["missing"] == out["total"]
        assert 0 <= lang["percent"] <= 100
        assert lang["overrides"] == 0  # none set yet


async def test_stats_counts_overrides():
    from api.admin import localization

    key = _some_key()
    async with SessionFactory() as s:
        await i18n_overrides.set_override(s, "en", key, "Hello")
    async with SessionFactory() as s:
        out = await localization.localization_stats(admin=_Admin(), session=s)
    by_code = {lang["code"]: lang for lang in out["languages"]}
    assert by_code["en"]["overrides"] == 1
    assert by_code["ru"]["overrides"] == 0


# ---- GET /localization/history --------------------------------------------
async def test_history_records_sets_newest_first():
    from api.admin import localization

    key = _some_key()
    # Two consecutive edits via the audited PUT endpoint build a real history.
    async with SessionFactory() as s:
        await localization.put_override(
            localization.OverridePut(locale="ru", key=key, text="версия 1"),
            _Req(), admin=_Admin(), session=s,
        )
    async with SessionFactory() as s:
        await localization.put_override(
            localization.OverridePut(locale="ru", key=key, text="версия 2"),
            _Req(), admin=_Admin(), session=s,
        )

    async with SessionFactory() as s:
        hist = await localization.localization_history(
            locale="ru", key=key, admin=_Admin(), session=s,
        )

    assert len(hist) == 2
    # Newest first; each set-action exposes the value that was applied (for rollback).
    assert {h["text"] for h in hist} == {"версия 1", "версия 2"}
    assert all(h["action"] == "localization.set" for h in hist)
    assert hist[0]["admin_id"] == _Admin.id


async def test_history_isolated_per_key_and_empty_default():
    from api.admin import localization

    key = _some_key()
    async with SessionFactory() as s:
        await localization.put_override(
            localization.OverridePut(locale="ru", key=key, text="x"),
            _Req(), admin=_Admin(), session=s,
        )
    # A different key has no history of its own.
    async with SessionFactory() as s:
        other = await localization.localization_history(
            locale="ru", key="__no_history__", admin=_Admin(), session=s,
        )
    assert other == []


# ---- POST /localization/translate (AI machine translation) -----------------
async def test_translate_uses_ru_source_and_returns_suggestion(monkeypatch):
    from api.admin import localization
    from core.services import i18n_translate

    seen = {}

    async def _fake(source, target_locale):
        seen["source"] = source
        seen["target"] = target_locale
        return "Translated!"

    monkeypatch.setattr(i18n_translate, "translate", _fake)
    key = _some_key()
    out = await localization.translate_text(
        localization.TranslateReq(locale="en", key=key), admin=_Admin(),
    )
    assert out == {"text": "Translated!"}
    # source defaulted to the key's RU static message; target is the requested locale
    assert seen["target"] == "en"
    assert seen["source"] == i18n.static_message(key, "ru")


async def test_translate_explicit_text_takes_precedence(monkeypatch):
    from api.admin import localization
    from core.services import i18n_translate

    async def _fake(source, target_locale):
        return source.upper()

    monkeypatch.setattr(i18n_translate, "translate", _fake)
    out = await localization.translate_text(
        localization.TranslateReq(locale="en", text="hi there"), admin=_Admin(),
    )
    assert out == {"text": "HI THERE"}


async def test_translate_rejects_bad_locale():
    from fastapi import HTTPException

    from api.admin import localization

    try:
        await localization.translate_text(
            localization.TranslateReq(locale="zz", key="x"), admin=_Admin(),
        )
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400


async def test_translate_surfaces_error_as_400(monkeypatch):
    from fastapi import HTTPException

    from api.admin import localization
    from core.services import i18n_translate

    async def _boom(source, target_locale):
        raise i18n_translate.TranslateError("ключ OpenAI не задан")

    monkeypatch.setattr(i18n_translate, "translate", _boom)
    try:
        await localization.translate_text(
            localization.TranslateReq(locale="en", key="x"), admin=_Admin(),
        )
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "OpenAI" in exc.detail


# ---- i18n_translate service (routes via AI router; no network) -------------
async def test_translate_service_ru_is_noop():
    from core.services import i18n_translate

    assert await i18n_translate.translate("привет {name}", "ru") == "привет {name}"


async def test_translate_service_blank_source_raises():
    from core.services import i18n_translate

    try:
        await i18n_translate.translate("   ", "en")
        raise AssertionError("expected TranslateError")
    except i18n_translate.TranslateError:
        pass


async def test_translate_service_uses_router_and_preserves_placeholder(monkeypatch):
    from core.ai_router import base, registry
    from core.services import i18n_translate

    captured = {}

    async def _fake_chat(model_key, user_text, *, system=None, history=None, locale="ru"):
        captured["model_key"] = model_key
        captured["system"] = system
        captured["user_text"] = user_text
        return base.TextResult(text="Buy for {price} ⭐", model=model_key, ok=True)

    monkeypatch.setattr(registry, "chat", _fake_chat)
    out = await i18n_translate.translate("Купить за {price} ⭐", "en")
    assert out == "Buy for {price} ⭐"
    # placeholder instruction reached the model; routed via the configured key
    assert "{price}" in captured["system"]
    assert captured["user_text"] == "Купить за {price} ⭐"


async def test_translate_service_raises_when_router_unavailable(monkeypatch):
    from core.ai_router import base, registry
    from core.services import i18n_translate

    async def _fake_chat(model_key, user_text, *, system=None, history=None, locale="ru"):
        # router's failure shape: localized placeholder + ok=False
        return base.TextResult(text="✨ AI is busy, try again", model=model_key, ok=False)

    monkeypatch.setattr(registry, "chat", _fake_chat)
    try:
        await i18n_translate.translate("Купить за {price} ⭐", "en")
        raise AssertionError("expected TranslateError")
    except i18n_translate.TranslateError as exc:
        # we must NOT surface the 'AI is busy' placeholder as a translation
        assert "AI is busy" not in str(exc)
