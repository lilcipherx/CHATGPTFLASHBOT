"""Higgsfield-style effect presets — cost math, model resolution, seed
integrity, and route mounting. Proves a preset routes to a real provider and
prices correctly off the existing service specs."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import select

import scripts.seed_catalogs as seed
from api.routers.miniapp import _allowed_models, _compute_cost
from core.ai_router.image_adapters import _IMAGE_PROVIDERS
from core.ai_router.image_specs import PHOTO_SPECS
from core.ai_router.video_adapters import provider_for
from core.ai_router.video_specs import VIDEO_SPECS
from core.db import SessionFactory, engine
from core.models import Base, MiniAppPhotoEffect, MiniAppVideoEffect


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def test_effect_routes_mounted():
    from api.main import app

    paths = {r.path for r in app.routes}
    assert "/api/effects" in paths
    assert "/api/effects/{kind}/{effect_id}" in paths
    assert "/api/effects/{kind}/{effect_id}/cost" in paths
    assert "/api/effects/{kind}/{effect_id}/generate" in paths
    assert "/api/admin/effects" in paths
    assert "/api/admin/effects/{kind}/{effect_id}/preview" in paths


def test_cost_photo_quality():
    assert _compute_cost("photo", "nano_banana", {"quality": "1k"}) == 2
    assert _compute_cost("photo", "nano_banana", {"quality": "2k"}) == 3
    assert _compute_cost("photo", "nano_banana", {"quality": "4k"}) == 4


def test_cost_video_duration_and_4k():
    assert _compute_cost("video", "kling_ai", {"duration": 5}) == 1
    assert _compute_cost("video", "kling_ai", {"duration": 10}) == 2
    assert _compute_cost("video", "kling_ai", {"duration": 10, "fourk": True}) == 4


def test_cost_unknown_model_defaults_to_one():
    assert _compute_cost("photo", "does_not_exist", {}) == 1
    assert _compute_cost("video", "", {"weird": 1}) == 1


def test_allowed_models_recommended_first_and_dedup():
    class Row:
        recommended_model = "kling_ai"
        compatible_models = ["veo", "kling_ai", "hailuo"]

    assert _allowed_models(Row()) == ["kling_ai", "veo", "hailuo"]


async def test_seed_presets_valid_priced_and_idempotent(monkeypatch):
    monkeypatch.setenv("CONFIRM", "1")  # skip the interactive destructive-wipe prompt
    await seed.main()
    await seed.main()  # delete+reinsert → idempotent
    async with SessionFactory() as s:
        photos = (await s.scalars(select(MiniAppPhotoEffect))).all()
        videos = (await s.scalars(select(MiniAppVideoEffect))).all()

    assert len(photos) == 12
    assert len(videos) == 12

    for p in photos:
        assert p.recommended_model in PHOTO_SPECS
        assert p.recommended_model in _IMAGE_PROVIDERS  # generate() can route it
        assert p.prompt_template and "{prompt}" in p.prompt_template
        assert all(m in PHOTO_SPECS for m in p.compatible_models)
        assert _compute_cost("photo", p.recommended_model, p.default_params) >= 1

    for v in videos:
        assert v.recommended_model in VIDEO_SPECS
        assert provider_for(v.recommended_model) is not None  # worker can route it
        assert v.prompt_template and "{prompt}" in v.prompt_template
        assert all(m in VIDEO_SPECS for m in v.compatible_models)
        assert _compute_cost("video", v.recommended_model, v.default_params) >= 1


async def test_seed_marks_trending_presets(monkeypatch):
    monkeypatch.setenv("CONFIRM", "1")  # skip the interactive destructive-wipe prompt
    await seed.main()
    async with SessionFactory() as s:
        trending = (await s.scalars(
            select(MiniAppVideoEffect).where(MiniAppVideoEffect.is_trending.is_(True))
        )).all()
    assert len(trending) >= 1
    assert all(t.enabled for t in trending)


# ---- preview upload: content-based validation (mirrors the banner normalizer) ----
import io  # noqa: E402
import types  # noqa: E402

from PIL import Image  # noqa: E402


def test_detect_video_ext_by_magic_bytes():
    from api.admin.effects import _detect_video_ext

    assert _detect_video_ext(b"\x00\x00\x00\x18ftypmp42rest") == ".mp4"
    assert _detect_video_ext(b"\x1a\x45\xdf\xa3rest-of-webm") == ".webm"
    assert _detect_video_ext(b"\x89PNG\r\n\x1a\n") is None  # an image, not video


class _FakeUpload:
    def __init__(self, data: bytes, filename: str = "x"):
        self._data, self.filename = data, filename

    async def read(self) -> bytes:
        return self._data


_REQ = types.SimpleNamespace(client=None)


async def _seed_photo_effect() -> int:
    async with SessionFactory() as s:
        e = MiniAppPhotoEffect(effect_id=1, category="all", name_ru="T")
        s.add(e)
        await s.commit()
        return e.effect_id


async def test_preview_upload_transcodes_gif_to_png(tmp_path, monkeypatch):
    from api.admin import effects as fx

    monkeypatch.setattr(fx, "_MEDIA_DIR", str(tmp_path))
    eid = await _seed_photo_effect()
    gif = io.BytesIO()
    Image.new("RGB", (8, 8), "teal").save(gif, format="GIF")
    admin = types.SimpleNamespace(id=1)
    async with SessionFactory() as s:
        out = await fx.upload_preview(
            "photo", eid, _REQ, file=_FakeUpload(gif.getvalue(), "a.gif"),
            admin=admin, session=s,
        )
    assert out["preview_url"].endswith(".png")  # GIF normalized to PNG


async def test_preview_upload_keeps_mp4_and_rejects_garbage(tmp_path, monkeypatch):
    from fastapi import HTTPException

    from api.admin import effects as fx

    monkeypatch.setattr(fx, "_MEDIA_DIR", str(tmp_path))
    eid = await _seed_photo_effect()
    admin = types.SimpleNamespace(id=1)
    mp4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 64
    async with SessionFactory() as s:
        out = await fx.upload_preview(
            "photo", eid, _REQ, file=_FakeUpload(mp4, "v.mp4"), admin=admin, session=s,
        )
    assert out["preview_url"].endswith(".mp4")  # video kept as-is

    async with SessionFactory() as s:
        try:
            await fx.upload_preview(
                "photo", eid, _REQ, file=_FakeUpload(b"not-media", "x.png"),
                admin=admin, session=s,
            )
            raised = False
        except HTTPException as e:
            raised = e.status_code == 400
        assert raised


async def test_admin_list_exposes_effective_price():
    """The admin list reports effective_price = override (>0) or the model's auto-cost,
    so the panel shows the real price even on 'авто'."""
    from api.admin.effects import list_effects

    async with SessionFactory() as s:
        # override=0 -> auto (nano_banana 1k = 2); a second with an explicit override.
        s.add(MiniAppPhotoEffect(effect_id=1, category="all", name_ru="Auto",
                                 recommended_model="nano_banana",
                                 default_params={"quality": "1k"}, price=0))
        s.add(MiniAppPhotoEffect(effect_id=2, category="all", name_ru="Fixed",
                                 recommended_model="nano_banana", price=7))
        await s.commit()
    admin = __import__("types").SimpleNamespace(id=1)
    async with SessionFactory() as s:
        out = await list_effects(kind="photo", admin=admin, session=s)
    by_id = {r["id"]: r for r in out}
    assert by_id[1]["price"] == 0 and by_id[1]["effective_price"] == 2   # auto cost
    assert by_id[2]["price"] == 7 and by_id[2]["effective_price"] == 7   # override wins


async def test_admin_model_specs_returns_param_schema():
    """The editor's friendly controls are built from /effects/specs/{kind}: each model
    exposes its option lists + flags + defaults (same source as the Mini App)."""
    from api.admin.effects import model_specs

    admin = __import__("types").SimpleNamespace(id=1)
    out = await model_specs(kind="video", admin=admin)
    models = out["models"]
    assert "kling_ai" in models or "seedance" in models
    # a known video model exposes durations + default; flags only when supported
    sd = models.get("seedance")
    if sd:
        assert "durations" in sd and isinstance(sd["default"], dict)
        assert sd.get("audio") is True

    photo = (await model_specs(kind="photo", admin=admin))["models"]
    nb = photo.get("nano_banana")
    if nb:
        assert "qualities" in nb and "count" in nb["default"]


# ---- preview required to ENABLE an effect (admin decision, ТЗ §13) ----------
from fastapi import HTTPException as _HTTPExc  # noqa: E402

_ADMIN = types.SimpleNamespace(id=1)


def _upsert(**kw):
    from api.admin.effects import EffectUpsert

    base = dict(name_ru="X", category="all", recommended_model="nano_banana")
    base.update(kw)
    return EffectUpsert(**base)


async def _create(kind="photo", **kw):
    from api.admin.effects import create_effect

    async with SessionFactory() as s:
        return await create_effect(_upsert(**kw), _REQ, kind=kind, admin=_ADMIN, session=s)


async def test_cannot_create_enabled_effect_without_preview():
    try:
        await _create(enabled=True)
        raised = False
    except _HTTPExc as e:
        raised = e.status_code == 400
    assert raised


async def test_enabled_effect_with_preview_ok():
    out = await _create(enabled=True, preview_url="/media/effects/x.png")
    assert out["enabled"] is True


async def test_enabled_effect_with_thumbnail_ok():
    out = await _create(enabled=True, thumbnail_url="/media/effects/t.png")
    assert out["enabled"] is True


async def test_disabled_draft_without_preview_ok():
    out = await _create(enabled=False)
    assert out["enabled"] is False and out["preview_url"] is None


async def test_update_cannot_enable_without_preview():
    from api.admin.effects import update_effect

    created = await _create(enabled=False)               # draft, no preview
    eid = created["id"]
    try:
        async with SessionFactory() as s:
            await update_effect("photo", eid, _upsert(enabled=True), _REQ,
                                admin=_ADMIN, session=s)
        raised = False
    except _HTTPExc as e:
        raised = e.status_code == 400
    assert raised


# ---- Trends is a hybrid: curated (is_trending) + organically popular (gen_count) --
async def test_trends_hybrid_curated_plus_popular_excludes_cold():
    from api.routers.miniapp import list_effects

    async with SessionFactory() as s:
        s.add(MiniAppVideoEffect(effect_id=1, category="all", name_ru="Curated",
                                 provider="kling", enabled=True, is_trending=True, gen_count=0))
        s.add(MiniAppVideoEffect(effect_id=2, category="all", name_ru="Popular",
                                 provider="kling", enabled=True, is_trending=False, gen_count=50))
        s.add(MiniAppVideoEffect(effect_id=3, category="all", name_ru="Cold",
                                 provider="kling", enabled=True, is_trending=False, gen_count=0))
        s.add(MiniAppVideoEffect(effect_id=4, category="all", name_ru="HiddenHot",
                                 provider="kling", enabled=False, is_trending=True, gen_count=99))
        await s.commit()

    tg = {"id": 1, "username": "u", "language_code": "ru"}
    async with SessionFactory() as s:
        out = await list_effects(kind="video", trending=True, tg=tg, session=s)
    ids = [r["id"] for r in out]
    assert 1 in ids and 2 in ids          # curated + organically popular shown
    assert 3 not in ids                   # neither flagged nor generated → not trending
    assert 4 not in ids                   # disabled effect never surfaces
    assert ids.index(1) < ids.index(2)    # curated ordered ahead of popular
