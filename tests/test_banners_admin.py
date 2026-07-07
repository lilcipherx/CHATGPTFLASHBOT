"""Carousel CMS admin endpoints — settings round-trip + enriched card.

Calls the endpoint coroutines directly against a seeded SQLite schema (no HTTP),
mirroring tests/test_broadcast_admin.py. Covers the no-migration backend additions
behind the reworked Carousel page:
  * GET "" exposes created_at + a sanitized behavior object (defaults when unset).
  * PUT /settings persists interval_ms (clamped) + behavior (sanitized) into the
    miniapp_carousel KV and round-trips it back.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException

from api.admin.banners import (
    BannerUpsert,
    CarouselSettingsReq,
    create_banner,
    list_banners,
    set_settings,
    update_banner,
)
from api.carousel import BEHAVIOR_DEFAULTS
from core.db import SessionFactory, engine
from core.models import AdminUser, Base, MiniAppBanner

_REQ = SimpleNamespace(client=None)


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _admin() -> AdminUser:
    async with SessionFactory() as s:
        a = AdminUser(email="cms@example.com", password_hash="x", role="admin")
        s.add(a)
        await s.commit()
        await s.refresh(a)
        return a


@pytest.mark.parametrize("bad", [
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    " javascript:alert(1)",
])
async def test_create_banner_rejects_non_http_link(bad):
    admin = await _admin()
    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await create_banner(
                BannerUpsert(image_url="/media/banners/a.png", link_url=bad),
                request=_REQ, admin=admin, session=s,
            )
        assert ei.value.status_code == 400


async def test_create_and_update_banner_accept_http_link():
    admin = await _admin()
    async with SessionFactory() as s:
        out = await create_banner(
            BannerUpsert(image_url="/media/banners/a.png",
                         link_url="https://t.me/mybot"),
            request=_REQ, admin=admin, session=s,
        )
        assert out["link_url"] == "https://t.me/mybot"
        bid = out["id"]
    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await update_banner(
                bid, BannerUpsert(link_url="javascript:alert(1)"),
                request=_REQ, admin=admin, session=s,
            )
        assert ei.value.status_code == 400


async def test_list_defaults_and_created_at():
    admin = await _admin()
    async with SessionFactory() as s:
        s.add(MiniAppBanner(image_url="/media/banners/a.png", title="Hi", sort_order=0))
        await s.commit()
    async with SessionFactory() as s:
        out = await list_banners(admin=admin, session=s)
    assert out["interval_ms"] == 5000
    assert out["behavior"] == BEHAVIOR_DEFAULTS          # defaults when KV unset
    assert out["banners"][0]["created_at"] is not None    # newly exposed field


async def test_settings_persist_and_sanitize():
    admin = await _admin()
    req = CarouselSettingsReq(
        interval_ms=999999,  # above MAX → clamped to 60000
        behavior={"animation": "fade", "speed_ms": 5000, "autoplay": False,
                  "show_arrows": True, "bogus": "x"},
    )
    async with SessionFactory() as s:
        res = await set_settings(req, request=_REQ, admin=admin, session=s)
    assert res["interval_ms"] == 60000
    assert res["behavior"]["animation"] == "fade"
    assert res["behavior"]["speed_ms"] == 2000          # clamped to max
    assert res["behavior"]["autoplay"] is False
    assert res["behavior"]["show_arrows"] is True
    assert "bogus" not in res["behavior"]                # unknown keys dropped

    # Round-trips through the KV on the next list.
    async with SessionFactory() as s:
        out = await list_banners(admin=admin, session=s)
    assert out["interval_ms"] == 60000
    assert out["behavior"]["animation"] == "fade"
    assert out["behavior"]["autoplay"] is False


async def test_settings_invalid_animation_falls_back():
    admin = await _admin()
    req = CarouselSettingsReq(interval_ms=4000, behavior={"animation": "zoom"})
    async with SessionFactory() as s:
        res = await set_settings(req, request=_REQ, admin=admin, session=s)
    assert res["interval_ms"] == 4000
    assert res["behavior"]["animation"] == "slide"       # invalid → default


async def test_admin_card_exposes_engagement_counters():
    admin = await _admin()
    async with SessionFactory() as s:
        out = await create_banner(
            BannerUpsert(image_url="/media/banners/a.png"),
            request=_REQ, admin=admin, session=s,
        )
    assert out["impressions"] == 0 and out["clicks"] == 0   # new rows start at zero


async def test_public_impression_and_click_increment_counters():
    """The Mini App reports engagement; counters increment atomically and the public
    /banners response carries the admin-managed behavior object."""
    from api.routers.miniapp import banner_click, banner_impression
    from api.routers.miniapp import banners as public_banners

    # tg is the verified initData dict (production reads tg["id"]); two distinct viewers
    # so the per-viewer dedup doesn't collapse the two impressions.
    tg1 = {"id": 1}
    tg2 = {"id": 2}
    async with SessionFactory() as s:
        b = MiniAppBanner(image_url="/media/banners/a.png", title="Hi", enabled=True)
        s.add(b)
        await s.commit()
        await s.refresh(b)
        bid = b.id

    async with SessionFactory() as s:
        await banner_impression(bid, tg=tg1, session=s)
        await banner_impression(bid, tg=tg2, session=s)
        await banner_impression(bid, tg=tg1, session=s)  # repeat viewer -> deduped
        await banner_click(bid, tg=tg1, session=s)

    async with SessionFactory() as s:
        b = await s.get(MiniAppBanner, bid)
        assert b.impressions == 2 and b.clicks == 1

    # Public payload includes behavior (defaults) alongside slides + interval.
    async with SessionFactory() as s:
        out = await public_banners(tg=tg1, session=s)
    assert out["behavior"]["animation"] == "slide"
    assert any(sl["id"] == bid for sl in out["slides"])


async def test_public_impression_unknown_id_is_noop():
    from api.routers.miniapp import banner_impression

    async with SessionFactory() as s:
        res = await banner_impression(999999, tg={"id": 1}, session=s)  # no row → silent ok
    assert res["ok"] is True


def test_normalize_image_passthrough_and_transcode_and_reject():
    """JPEG/PNG/WEBP pass through; other decodable formats (GIF) transcode to PNG;
    non-images are rejected (None)."""
    import io

    from PIL import Image

    from api.images import _detect_image_ext, _normalize_image

    png = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(png, format="PNG")
    out, ext = _normalize_image(png.getvalue())
    assert ext == ".png" and out == png.getvalue()       # PNG passes through unchanged

    gif = io.BytesIO()
    Image.new("RGB", (4, 4), "blue").save(gif, format="GIF")
    out, ext = _normalize_image(gif.getvalue())
    assert ext == ".png" and _detect_image_ext(out) == ".png"   # GIF → PNG

    assert _normalize_image(b"not an image at all") is None     # rejected


class _FakeUpload:
    def __init__(self, data: bytes, filename: str = "x.gif"):
        self._data, self.filename = data, filename

    async def read(self) -> bytes:
        return self._data


async def test_banner_image_upload_transcodes_gif(tmp_path, monkeypatch):
    """Uploading a GIF stores a renderable .png (not a dead file or a 400)."""
    import io

    from PIL import Image

    from api.admin import banners as banners_mod

    monkeypatch.setattr(banners_mod, "_MEDIA_DIR", str(tmp_path))
    admin = await _admin()
    async with SessionFactory() as s:
        b = MiniAppBanner(image_url="", title="g", enabled=True)
        s.add(b)
        await s.commit()
        await s.refresh(b)
        bid = b.id

    gif = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(gif, format="GIF")
    async with SessionFactory() as s:
        out = await banners_mod.upload_image(
            bid, request=_REQ, file=_FakeUpload(gif.getvalue()), admin=admin, session=s,
        )
    assert out["image_url"].endswith(".png")


# ---- per-slide locale targeting (CMS carousel localization) ----------------
from api.admin.banners import _norm_locale  # noqa: E402


def test_norm_locale_keeps_supported_else_none():
    assert _norm_locale("en") == "en"
    assert _norm_locale("RU") == "ru"
    assert _norm_locale("") is None
    assert _norm_locale("all") is None
    assert _norm_locale("zz") is None
    assert _norm_locale(None) is None


async def test_create_banner_stores_normalized_locale():
    admin = await _admin()
    async with SessionFactory() as s:
        out = await create_banner(
            BannerUpsert(image_url="/media/b.png", title="EN slide", locale="EN"),
            _REQ, admin=admin, session=s,
        )
        assert out["locale"] == "en"
        # unknown locale → None (shown to all)
        out2 = await create_banner(
            BannerUpsert(image_url="/media/c.png", title="all", locale="xx"),
            _REQ, admin=admin, session=s,
        )
        assert out2["locale"] is None


async def test_carousel_filters_by_locale():
    from api.routers import miniapp

    admin = await _admin()
    async with SessionFactory() as s:
        await create_banner(
            BannerUpsert(image_url="/media/all.png", title="all"),
            _REQ, admin=admin, session=s)
        await create_banner(
            BannerUpsert(image_url="/media/ru.png", title="ru", locale="ru"),
            _REQ, admin=admin, session=s)
        await create_banner(
            BannerUpsert(image_url="/media/en.png", title="en", locale="en"),
            _REQ, admin=admin, session=s)

    async with SessionFactory() as s:
        en = await miniapp.banners(locale="en", tg=None, session=s)
        ru = await miniapp.banners(locale="ru", tg=None, session=s)
        none = await miniapp.banners(locale=None, tg=None, session=s)
    en_titles = {x["title"] for x in en["slides"]}
    ru_titles = {x["title"] for x in ru["slides"]}
    assert en_titles == {"all", "en"}      # NULL-locale + matching only
    assert ru_titles == {"all", "ru"}
    assert "en" not in ru_titles           # other-locale slide hidden
    # no locale param → all slides (back-compat)
    assert {x["title"] for x in none["slides"]} == {"all", "ru", "en"}
