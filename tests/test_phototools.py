"""Тесты сервисного слоя фото-инструментов (ТЗ §5): реестр, цены, отказ при
отсутствии провайдера.

Чистые unit-тесты + один интеграционный с live-конфигом цен через SessionFactory
(паттерн tests/test_admins). Сеть не дёргается: провайдер не настроен, а адаптеры —
заглушки.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from core.ai_router.base import ProviderUnavailable  # FIX: B15 - H6 changed run() to raise
from core.db import SessionFactory, engine
from core.models import Base
from core.services import phototools as pt


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


# ---- реестр -----------------------------------------------------------------
def test_registry_complete():
    """Каждый PhotoTool имеет ToolSpec с непустым названием и валидной ценой."""
    assert set(pt.REGISTRY) == set(pt.PhotoTool)
    for tool, spec in pt.REGISTRY.items():
        assert spec.tool is tool
        assert spec.key == tool.value
        assert spec.title.strip()
        assert spec.default_price >= 0
    assert {s.key for s in pt.all_specs()} == {"face_swap", "upscale", "avatars"}


def test_resolve_by_enum_and_str():
    assert pt.resolve(pt.PhotoTool.UPSCALE) is pt.REGISTRY[pt.PhotoTool.UPSCALE]
    assert pt.resolve("face_swap") is pt.REGISTRY[pt.PhotoTool.FACE_SWAP]
    assert pt.resolve("does_not_exist") is None


# ---- цены -------------------------------------------------------------------
async def test_price_defaults():
    """Без override'ов в БД цена = default_price реестра."""
    async with SessionFactory() as s:
        assert await pt.price(s, pt.PhotoTool.FACE_SWAP) == 1
        assert await pt.price(s, "upscale") == 2
        assert await pt.price(s, pt.PhotoTool.AVATARS) == 200
    assert await _price_unknown() is None


async def _price_unknown():
    async with SessionFactory() as s:
        return await pt.price(s, "nope")


async def test_price_from_config_override(monkeypatch):
    """Цена берётся из live-конфига (блок phototools), перекрывая дефолт."""
    async def fake_cfg(_session):
        return {pt.CONFIG_KEY: {"face_swap": 7, "upscale": "x"}}

    monkeypatch.setattr("core.services.pricing.get_config", fake_cfg)
    async with SessionFactory() as s:
        assert await pt.price(s, "face_swap") == 7          # override применён
        assert await pt.price(s, "upscale") == 2            # мусор → откат на default
        assert await pt.price(s, "avatars") == 200          # нет в блоке → default


# ---- run(): provider_unavailable -------------------------------------------
async def test_run_provider_unavailable(monkeypatch):
    """Без ключа провайдера run() поднимает ProviderUnavailable (FIX: B15 / H6)."""
    monkeypatch.setattr(pt, "_provider_key", lambda: "")
    assert not pt.provider_available()
    with pytest.raises(ProviderUnavailable):
        await pt.run(pt.PhotoTool.FACE_SWAP, "http://example/img.png")


async def test_run_unknown_tool():
    res = await pt.run("totally_unknown", "http://example/img.png")
    assert res.ok is False
    assert res.reason == pt.REASON_UNKNOWN_TOOL


async def test_run_bad_input(monkeypatch):
    """Пустой image_url → bad_input, даже если ключ настроен."""
    monkeypatch.setattr(pt, "_provider_key", lambda: "secret")
    res = await pt.run(pt.PhotoTool.UPSCALE, "")
    assert res.ok is False
    assert res.reason == pt.REASON_BAD_INPUT


async def test_run_dispatches_to_adapter_when_available(monkeypatch):
    """С настроенным ключом run() диспатчит в адаптер и возвращает его ToolResult."""
    monkeypatch.setattr(pt, "_provider_key", lambda: "secret")

    async def ok_adapter(image_url, **opts):
        return pt.ToolResult(ok=True, url="http://out/result.png", meta={"opts": opts})

    monkeypatch.setitem(pt._ADAPTERS, pt.PhotoTool.UPSCALE, ok_adapter)
    res = await pt.run(pt.PhotoTool.UPSCALE, "http://in/img.png", factor="x4")
    assert res.ok is True
    assert res.url == "http://out/result.png"
    assert res.meta["opts"] == {"factor": "x4"}


async def test_run_adapter_error_is_soft(monkeypatch):
    """Исключение из адаптера превращается в ToolResult(reason=provider_error)."""
    monkeypatch.setattr(pt, "_provider_key", lambda: "secret")

    async def boom(image_url, **opts):
        raise RuntimeError("provider blew up")

    monkeypatch.setitem(pt._ADAPTERS, pt.PhotoTool.AVATARS, boom)
    res = await pt.run(pt.PhotoTool.AVATARS, "http://in/img.png")
    assert res.ok is False
    assert res.reason == pt.REASON_PROVIDER_ERROR


def test_default_adapters_are_unavailable():
    """В дефолтной поставке (без реальных провайдеров) все адаптеры — заглушки."""
    assert set(pt._ADAPTERS) == set(pt.PhotoTool)


@pytest.mark.parametrize("tool", list(pt.PhotoTool))
async def test_run_provider_unavailable_all_tools(tool, monkeypatch):
    monkeypatch.setattr(pt, "_provider_key", lambda: "")
    with pytest.raises(ProviderUnavailable):  # FIX: B15 / H6
        await pt.run(tool, "http://example/img.png")
