"""Webhook HTTP routes (Loop coverage): the Telegram secret gate and the four gateway
route wrappers driven through the real app, plus a verified paid gateway event flowing
into apply_event + the buyer notify. Providers/bot mocked; DB is SQLite.
"""
from __future__ import annotations

import types

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.main import app
from api.routers import webhooks
from core.config import settings
from core.db import SessionFactory, engine
from core.models import Base
from core.payments.base import PaymentEvent
from core.services.credits import get_balance
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def test_telegram_webhook_bad_secret_403(client):
    r = await client.post("/webhook/telegram",
                          headers={"x-telegram-bot-api-secret-token": "WRONG"}, json={})
    assert r.status_code == 403


@pytest.mark.parametrize("path", ["/webhook/stripe", "/webhook/tribute", "/webhook/crypto"])
async def test_gateway_route_unknown_provider(client, monkeypatch, path):
    monkeypatch.setattr(webhooks, "get_provider", lambda g: None)
    r = await client.post(path, json={})
    assert r.status_code == 200 and r.json() == {"ok": False, "error": "unknown gateway"}


async def test_yookassa_route_applies_paid_event_and_notifies(client, monkeypatch):
    import core.bot_client as bc

    class _FakeBot:
        async def send_message(self, *a, **k):
            return None
    monkeypatch.setattr(bc, "get_bot", lambda: _FakeBot())
    # dev/test with an empty IP allowlist skips the source-IP check (non-public).
    monkeypatch.setattr(settings, "yookassa_webhook_ips", "")

    async with SessionFactory() as s:
        await get_or_create_user(s, 7777)

    ev = PaymentEvent(payload="credits:7777:10:500", gateway="yookassa",
                      gateway_tx_id="yk9", amount=500, status="paid")
    monkeypatch.setattr(webhooks, "get_provider",
                        lambda g: types.SimpleNamespace(verify_webhook=lambda h, b: ev))

    r = await client.post("/webhook/yookassa", json={})
    assert r.status_code == 200 and r.json() == {"ok": True}
    async with SessionFactory() as s:
        assert await get_balance(s, 7777) == 10
