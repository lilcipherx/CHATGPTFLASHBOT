"""Integration: the Telegram webhook must be idempotent against redelivery.

Telegram retries a webhook delivery on any non-2xx OR timeout. A slow turn (an AI
call bounded at ~60s) can be redelivered while the first is still processing; without
update_id dedup the handler would run twice — double quota charge, double provider
cost, double reply. This drives the real endpoint through a fake dispatcher and
asserts a redelivered update_id is fed exactly once.
"""
from __future__ import annotations

import pytest

from api.routers import webhooks
from core.config import settings
from core.redis_client import redis_client


class _FakeBot:
    id = 555000111


class _FakeDp:
    def __init__(self):
        self.fed: list[int] = []

    async def feed_update(self, bot, update):
        self.fed.append(update.update_id)


class _State:
    def __init__(self, bot, dp):
        self.bot, self.dp = bot, dp


class _App:
    def __init__(self, bot, dp):
        self.state = _State(bot, dp)


class _Req:
    def __init__(self, app, body: dict, secret: str):
        self.app = app
        self._body = body
        self.headers = {"x-telegram-bot-api-secret-token": secret}

    async def json(self):
        return self._body


def _update(update_id: int) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 1, "type": "private"},
            "from": {"id": 1, "is_bot": False, "first_name": "t"},
            "text": "hi",
        },
    }


@pytest.mark.asyncio
async def test_redelivered_update_is_processed_once(monkeypatch):
    # Isolate the dedup keys from any prior run.
    for k in await redis_client.keys("tg:wh:*"):
        await redis_client.delete(k)

    bot, dp = _FakeBot(), _FakeDp()
    app = _App(bot, dp)
    secret = settings.effective_webhook_secret

    # Avoid building a real aiogram Update: validate() just needs the update_id.
    class _U:
        def __init__(self, update_id):
            self.update_id = update_id

    monkeypatch.setattr(
        webhooks.Update, "model_validate",
        classmethod(lambda cls, data, context=None: _U(data["update_id"])),
    )

    r1 = await webhooks.telegram_webhook(_Req(app, _update(42), secret))
    r2 = await webhooks.telegram_webhook(_Req(app, _update(42), secret))  # redelivery
    r3 = await webhooks.telegram_webhook(_Req(app, _update(43), secret))  # new update

    assert r1.status_code == r2.status_code == r3.status_code == 200
    # Update 42 fed exactly once despite two deliveries; 43 fed once.
    assert dp.fed == [42, 43]


@pytest.mark.asyncio
async def test_bad_secret_is_rejected_before_feeding(monkeypatch):
    bot, dp = _FakeBot(), _FakeDp()
    app = _App(bot, dp)
    resp = await webhooks.telegram_webhook(_Req(app, _update(99), "wrong-secret"))
    assert resp.status_code == 403
    assert dp.fed == []
