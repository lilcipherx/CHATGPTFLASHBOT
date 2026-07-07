"""Live localization editor (ТЗ §8) — text overrides over the static i18n dicts.

Verifies that an admin override is read live by the SYNCHRONOUS translator (after the
in-memory snapshot refresh), that clearing reverts to the static message, that a blank/
unknown override never breaks ``t``, that a locale with no overrides is byte-identical to
static, and the admin endpoint coroutines (merged map / put / delete).
"""
from __future__ import annotations

import pytest
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
    # Start every test from an empty snapshot (no leak between tests).
    await i18n_overrides.load_once()
    yield
    # Clear the snapshot and drop the fakeredis connection bound to this loop.
    await i18n_overrides.load_once()
    try:
        await i18n_overrides.redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


# Pick a real key that exists in the static dicts so we test against actual content.
def _some_key() -> str:
    return i18n.known_keys()[0]


async def test_no_overrides_is_identical_to_static():
    key = _some_key()
    for loc in ("ru", "en"):
        assert i18n.t(key, loc) == i18n.static_message(key, loc)
    # A locale with no overrides behaves exactly like the static dict.
    assert i18n_overrides.snapshot() == {}


async def test_override_applies_after_refresh():
    key = _some_key()
    async with SessionFactory() as s:
        await i18n_overrides.set_override(s, "ru", key, "ПЕРЕОПРЕДЕЛЕНО")
    # set_override refreshes the snapshot in-process; the sync translator sees it.
    assert i18n.t(key, "ru") == "ПЕРЕОПРЕДЕЛЕНО"
    # Another locale (no override for it) is untouched.
    assert i18n.t(key, "en") == i18n.static_message(key, "en")


async def test_clear_reverts_to_static():
    key = _some_key()
    static = i18n.static_message(key, "ru")
    async with SessionFactory() as s:
        await i18n_overrides.set_override(s, "ru", key, "X")
    assert i18n.t(key, "ru") == "X"
    async with SessionFactory() as s:
        existed = await i18n_overrides.clear_override(s, "ru", key)
    assert existed is True
    assert i18n.t(key, "ru") == static


async def test_blank_and_unknown_overrides_never_break_t():
    async with SessionFactory() as s:
        with pytest.raises(ValueError):
            await i18n_overrides.set_override(s, "ru", "  ", "x")
        with pytest.raises(ValueError):
            await i18n_overrides.set_override(s, "xx", "anything", "x")
    # An override on a key that isn't in any static dict still resolves to that text.
    async with SessionFactory() as s:
        await i18n_overrides.set_override(s, "ru", "__brand_new_key__", "Hello")
    assert i18n.t("__brand_new_key__", "ru") == "Hello"
    # An unknown key with NO override returns the key itself (unchanged behaviour).
    assert i18n.t("__never_set__", "ru") == "__never_set__"


async def test_clear_nonexistent_returns_false():
    async with SessionFactory() as s:
        assert await i18n_overrides.clear_override(s, "ru", "__nope__") is False


# ---- admin endpoint coroutines ---------------------------------------------
class _Admin:
    id = 1


class _Req:
    client = None


async def test_endpoint_get_merged_map():
    from api.admin import localization

    key = _some_key()
    async with SessionFactory() as s:
        await i18n_overrides.set_override(s, "ru", key, "OVR")
    async with SessionFactory() as s:
        data = await localization.get_localization(locale="ru", admin=_Admin(), session=s)
    assert data["locale"] == "ru"
    assert any(loc["code"] == "ru" for loc in data["locales"])
    by_key = {it["key"]: it for it in data["items"]}
    assert by_key[key]["override"] == "OVR"
    assert by_key[key]["default"] == i18n.static_message(key, "ru")


async def test_endpoint_put_and_delete():
    from api.admin import localization

    key = _some_key()
    body = localization.OverridePut(locale="ru", key=key, text="ВРУЧНУЮ")
    async with SessionFactory() as s:
        res = await localization.put_override(body, _Req(), admin=_Admin(), session=s)
    assert res["ok"] is True
    assert i18n.t(key, "ru") == "ВРУЧНУЮ"

    async with SessionFactory() as s:
        res = await localization.delete_override(
            locale="ru", key=key, request=_Req(), admin=_Admin(), session=s,
        )
    assert res["ok"] is True and res["existed"] is True
    assert i18n.t(key, "ru") == i18n.static_message(key, "ru")
