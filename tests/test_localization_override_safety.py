"""Localization overrides must never crash the bot, and bad overrides are rejected
at write time.

* Render time (core.i18n.t): a stored override carrying an unknown {placeholder}
  is caught and the static message is used instead — str.format never propagates.
* Write time (admin PUT /localization): an override that introduces a placeholder
  the static default doesn't have, or a malformed brace, is rejected with 400.
"""
from __future__ import annotations

import types

import pytest
import pytest_asyncio
from fastapi import HTTPException

from api.admin import localization
from core import i18n
from core.db import SessionFactory, engine
from core.models import Base


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req():
    return types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))


class _Admin:
    id = 1
    role = "admin"


def _key_without_placeholders() -> str:
    for k in i18n.known_keys():
        if not localization._placeholders(i18n.static_message(k, "ru") or ""):
            return k
    raise AssertionError("no placeholder-free key found")


# ---- render-time guard -----------------------------------------------------
def test_t_does_not_raise_on_bad_override(monkeypatch):
    key = _key_without_placeholders()
    # Simulate a stored override with an unknown placeholder (set_override does not
    # validate; the admin endpoint does, but a legacy/raw value must still be safe).
    monkeypatch.setattr(i18n, "_override", lambda loc, k: "{nope}" if k == key else None)
    out = i18n.t(key, locale="ru", anything="x")  # must NOT raise
    assert isinstance(out, str)
    assert "{nope}" not in out  # fell back to the static message


def test_t_does_not_raise_on_malformed_override(monkeypatch):
    key = _key_without_placeholders()
    monkeypatch.setattr(i18n, "_override", lambda loc, k: "broken {" if k == key else None)
    out = i18n.t(key, locale="ru", anything="x")
    assert isinstance(out, str)


# ---- write-time validation -------------------------------------------------
async def test_put_override_rejects_unknown_placeholder():
    key = _key_without_placeholders()
    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await localization.put_override(
                localization.OverridePut(locale="ru", key=key, text="Hello {foo}"),
                _req(), admin=_Admin(), session=s,
            )
        assert ei.value.status_code == 400


async def test_put_override_rejects_malformed_brace():
    key = _key_without_placeholders()
    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await localization.put_override(
                localization.OverridePut(locale="ru", key=key, text="oops {"),
                _req(), admin=_Admin(), session=s,
            )
        assert ei.value.status_code == 400


async def test_put_override_accepts_plain_text():
    key = _key_without_placeholders()
    async with SessionFactory() as s:
        out = await localization.put_override(
            localization.OverridePut(locale="ru", key=key, text="простой текст"),
            _req(), admin=_Admin(), session=s,
        )
        assert out["ok"] is True
