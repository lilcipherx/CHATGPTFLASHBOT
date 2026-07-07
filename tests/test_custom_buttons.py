"""Custom inline link buttons (ТЗ §8 «конструктор кнопок»).

Covers (a) the live-config getter ``pricing.custom_buttons`` (default empty,
reflects an admin override, drops malformed entries) and (b) the pure keyboard
builder ``build_links_keyboard`` (valid URLs included, bad schemes skipped,
empty -> None).
"""
from __future__ import annotations

import pytest_asyncio

import core.models  # noqa: F401 — registers every table on Base.metadata
from bot.handlers.links import build_links_keyboard
from core.db import SessionFactory, engine
from core.models import Base
from core.services import pricing


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield
    try:
        await pricing.redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


async def test_custom_buttons_default_empty():
    async with SessionFactory() as s:
        assert await pricing.custom_buttons(s) == []


async def test_custom_buttons_reflects_override_and_drops_malformed():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"custom_buttons": [
            {"text": "Канал", "url": "https://t.me/example"},
            {"text": "", "url": "https://t.me/empty_text"},   # missing text -> dropped
            {"text": "No URL"},                                # missing url -> dropped
            "not-a-dict",                                      # malformed -> dropped
        ]})
    async with SessionFactory() as s:
        out = await pricing.custom_buttons(s)
    assert out == [{"text": "Канал", "url": "https://t.me/example"}]


def test_build_links_keyboard_includes_valid_skips_invalid():
    kb = build_links_keyboard([
        {"text": "HTTPS", "url": "https://example.com"},
        {"text": "HTTP", "url": "http://example.com"},
        {"text": "Telegram", "url": "tg://resolve?domain=example"},
        {"text": "Bad scheme", "url": "javascript:alert(1)"},
        {"text": "No url", "url": ""},
        {"text": "", "url": "https://no-text.example"},
    ])
    assert kb is not None
    texts = [row[0].text for row in kb.inline_keyboard]
    assert texts == ["HTTPS", "HTTP", "Telegram"]
    # one URL button per row
    assert all(len(row) == 1 for row in kb.inline_keyboard)


def test_build_links_keyboard_empty_returns_none():
    assert build_links_keyboard([]) is None
    assert build_links_keyboard([{"text": "x", "url": "ftp://nope"}]) is None


def test_build_links_keyboard_groups_rows_and_prefixes_icon():
    kb = build_links_keyboard([
        {"text": "ChatGPT", "url": "https://a.com", "row": 0, "icon": "🤖"},
        {"text": "Claude", "url": "https://b.com", "row": 0},
        {"text": "Support", "url": "https://c.com", "row": 1},
        {"text": "No row", "url": "https://d.com"},   # own row (row absent)
    ])
    assert kb is not None
    layout = [[btn.text for btn in row] for row in kb.inline_keyboard]
    assert layout == [["🤖 ChatGPT", "Claude"], ["Support"], ["No row"]]


def test_build_links_keyboard_skips_disabled():
    kb = build_links_keyboard([
        {"text": "On", "url": "https://a.com"},
        {"text": "Off", "url": "https://b.com", "enabled": False},
    ])
    assert kb is not None
    assert [row[0].text for row in kb.inline_keyboard] == ["On"]


async def test_custom_buttons_passes_through_layout_fields():
    async with SessionFactory() as s:
        await pricing.set_config(s, {"custom_buttons": [
            {"text": "A", "url": "https://a.com", "row": 0, "icon": "🔥",
             "enabled": True, "color": "lime", "type": "https"},
            {"text": "B", "url": "https://b.com", "enabled": False},
        ]})
    async with SessionFactory() as s:
        out = await pricing.custom_buttons(s)
    # text/url always; row/icon passed through; enabled only when False; admin-only
    # metadata (color/type) dropped by the getter.
    assert out[0] == {"text": "A", "url": "https://a.com", "row": 0, "icon": "🔥"}
    assert out[1] == {"text": "B", "url": "https://b.com", "enabled": False}


async def test_custom_buttons_passes_through_stable_id():
    """The stable id (used by the /r/{id} click tracker) survives the getter."""
    async with SessionFactory() as s:
        await pricing.set_config(s, {"custom_buttons": [
            {"id": "btn_abc", "text": "A", "url": "https://a.com"},
        ]})
    async with SessionFactory() as s:
        out = await pricing.custom_buttons(s)
    assert out[0] == {"id": "btn_abc", "text": "A", "url": "https://a.com"}


def test_build_links_keyboard_routes_http_through_tracker_when_base_set():
    """With a public base + stable id, http(s) buttons point at /r/{id}; tg:// keeps
    its raw URL (can't 302 a deep link); ids/base absent => raw URL unchanged."""
    buttons = [
        {"id": "b1", "text": "Site", "url": "https://example.com"},
        {"id": "b2", "text": "Deep", "url": "tg://resolve?domain=x"},
        {"text": "NoId", "url": "https://noid.com"},
    ]
    kb = build_links_keyboard(buttons, redirect_base="https://bot.example.com/")
    urls = [row[0].url for row in kb.inline_keyboard]
    assert urls == [
        "https://bot.example.com/r/b1",   # tracked
        "tg://resolve?domain=x",          # tg:// untouched
        "https://noid.com",               # no id -> raw
    ]
    # No base -> every button keeps its raw URL (local polling dev).
    kb2 = build_links_keyboard(buttons)
    assert [row[0].url for row in kb2.inline_keyboard] == [
        "https://example.com", "tg://resolve?domain=x", "https://noid.com",
    ]


async def test_redirect_tracks_click_and_302s():
    from types import SimpleNamespace

    from fastapi import HTTPException

    from api.routers.redirect import track_and_redirect
    from core.models import CustomButtonStat

    # The click count is deduped per IP/hour, so two taps from DIFFERENT IPs to count 2.
    req1 = SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"))
    req2 = SimpleNamespace(client=SimpleNamespace(host="10.0.0.2"))

    async with SessionFactory() as s:
        await pricing.set_config(s, {"custom_buttons": [
            {"id": "b1", "text": "Site", "url": "https://example.com"},
        ]})
    async with SessionFactory() as s:
        r1 = await track_and_redirect("b1", request=req1, session=s)
        assert r1.status_code == 302 and r1.headers["location"] == "https://example.com"
    async with SessionFactory() as s:
        await track_and_redirect("b1", request=req2, session=s)  # second tap, other IP
    async with SessionFactory() as s:
        stat = await s.get(CustomButtonStat, "b1")
        assert stat.clicks == 2

    # A repeat tap from the SAME IP within the window does not double-count.
    async with SessionFactory() as s:
        await track_and_redirect("b1", request=req1, session=s)
    async with SessionFactory() as s:
        stat = await s.get(CustomButtonStat, "b1")
        assert stat.clicks == 2

    # Unknown id -> 404, no row created.
    async with SessionFactory() as s:
        try:
            await track_and_redirect("nope", request=req1, session=s)
            raised = False
        except HTTPException as e:
            raised = e.status_code == 404
        assert raised
