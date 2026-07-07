"""Работа в группах (ТЗ §3): чистые хелперы is_addressed/strip_mention + дефолт
groups_enabled=False в pricing.chat_config."""
from __future__ import annotations

import pytest_asyncio

from bot.handlers.groups import is_addressed, strip_mention
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


def test_is_addressed_mention_present():
    assert is_addressed("привет @MyBot как дела", "MyBot", False) is True


def test_is_addressed_reply_to_bot():
    assert is_addressed("без упоминания", "MyBot", True) is True


def test_is_addressed_neither():
    assert is_addressed("обычная болтовня", "MyBot", False) is False


def test_is_addressed_case_insensitive():
    assert is_addressed("эй @mybot ответь", "MyBot", False) is True


def test_is_addressed_no_username():
    # Нет имени бота и нет reply → обратиться невозможно.
    assert is_addressed("@MyBot", "", False) is False


def test_strip_mention_removes_and_trims():
    assert strip_mention("@MyBot расскажи анекдот", "MyBot") == "расскажи анекдот"


def test_strip_mention_case_insensitive():
    assert strip_mention("вопрос @MYBOT тут", "MyBot") == "вопрос  тут".strip()


def test_strip_mention_no_username_just_trims():
    assert strip_mention("  текст  ", "") == "текст"


async def test_chat_config_groups_enabled_default_true():
    # Full-product launch: the bot answers in group chats by default (admin can
    # still turn this off via chat.groups_enabled).
    async with SessionFactory() as s:
        cfg = await pricing.chat_config(s)
    assert cfg["groups_enabled"] is True
