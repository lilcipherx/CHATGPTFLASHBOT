"""Process-wide shared aiogram Bot.

A single Bot owns one aiohttp ClientSession (connection pool). Creating a fresh
Bot per call — as the webhook notifier, the Mini App invoice endpoint and the
admin refund path used to — opens and tears down a TCP/TLS session for every
message, which wastes CPU and can exhaust sockets under bursts (broadcasts, a
flood of payment webhooks). This module hands out one cached Bot per process and
closes it on shutdown.

Safe as a module-level singleton: each process (gunicorn/uvicorn worker, the bot
process) has its own event loop, and the Bot's session binds lazily to the loop
it is first used on.
"""
from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from core.config import settings

_bot: Bot | None = None


def get_bot() -> Bot:
    """Return the shared Bot, creating it on first use (HTML parse mode, matching
    the dispatcher's bot in bot.main)."""
    global _bot
    if _bot is None:
        _bot = Bot(
            token=settings.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
    return _bot


async def close_bot() -> None:
    """Close the shared Bot's session. Call on process shutdown."""
    global _bot
    if _bot is not None:
        await _bot.session.close()
        _bot = None
