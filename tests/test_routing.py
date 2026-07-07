"""Routing audit: every command, reply-button (all locales) and callback must
resolve to a handler through the real dispatcher filters."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiogram import Bot
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TgUser

from bot.main import COMMAND_ORDER, build_dispatcher
from core.constants import SUPPORTED_LOCALES
from core.i18n import t

BUTTON_KEYS = [
    "btn.model", "btn.images", "btn.search", "btn.video",
    "btn.documents", "btn.music", "btn.premium", "btn.account",
]
CALLBACKS = [
    "close", "premium:open", "prem:premium", "premdur:premium:1",
    "pay:stars:premium:1", "pay:yookassa:premium:1", "pack:image_pack",
    "packqty:image_pack:50", "packpay:stars:image_pack:50",
    "settings:open", "settings:model", "settings:role", "settings:context",
    "settings:voice", "settings:lang", "lang:en", "voice:set:nova",
    "voice:toggle", "voice:preview", "model:gpt_5_mini", "photo:gpt_image2",
    "photo:back", "video:kling_effects", "video:kling_motion", "video:seedance",
    "music:suno", "avatar:buy", "keff:page:2", "keff:sel:1", "kmot:sel:1",
]


@pytest.fixture(scope="module")
def bot_dp():
    bot = Bot("123456:FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE")
    dp = build_dispatcher()
    return bot, dp


def _routers(r):
    yield r
    for sr in r.sub_routers:
        yield from _routers(sr)


async def _matches(dp, bot, event, observer: str) -> bool:
    for r in _routers(dp):
        for h in getattr(r, observer).handlers:
            try:
                ok, _ = await h.check(event, bot=bot, event_from_user=event.from_user)
            except Exception:  # noqa: BLE001
                ok = False
            if ok:
                return True
    return False


def _msg(bot, text):
    return Message(
        message_id=1, date=datetime.now(UTC), chat=Chat(id=1, type="private"),
        from_user=TgUser(id=1, is_bot=False, first_name="t"), text=text,
    ).as_(bot)


def _cb(bot, data):
    return CallbackQuery(
        id="1", from_user=TgUser(id=1, is_bot=False, first_name="t"),
        chat_instance="x", data=data,
    ).as_(bot)


async def test_all_commands_route(bot_dp):
    bot, dp = bot_dp
    for c in COMMAND_ORDER:
        assert await _matches(dp, bot, _msg(bot, f"/{c}"), "message"), f"/{c} unrouted"


async def test_all_reply_buttons_route_in_every_locale(bot_dp):
    bot, dp = bot_dp
    for loc in SUPPORTED_LOCALES:
        for key in BUTTON_KEYS:
            label = t(key, loc)
            assert await _matches(dp, bot, _msg(bot, label), "message"), \
                f"button {key} ({loc}: {label}) unrouted"


async def test_all_callbacks_route(bot_dp):
    bot, dp = bot_dp
    for data in CALLBACKS:
        assert await _matches(dp, bot, _cb(bot, data), "callback_query"), f"{data} unrouted"


async def _first_handler_module(dp, bot, event, observer: str) -> str | None:
    for r in _routers(dp):
        for h in getattr(r, observer).handlers:
            try:
                ok, _ = await h.check(event, bot=bot, event_from_user=event.from_user)
            except Exception:  # noqa: BLE001
                ok = False
            if ok:
                return h.callback.__module__
    return None


async def test_video_callbacks_resolve_to_correct_module(bot_dp):
    """Guards against an earlier router shadowing the real video/kling handlers."""
    bot, dp = bot_dp
    cases = {
        "video:seedance": "bot.handlers.video",
        "video:veo": "bot.handlers.video",
        "video:kling_effects": "bot.handlers.kling",
        "video:kling_motion": "bot.handlers.kling",
    }
    for data, expected in cases.items():
        mod = await _first_handler_module(dp, bot, _cb(bot, data), "callback_query")
        assert mod == expected, f"{data} handled by {mod}, expected {expected}"
