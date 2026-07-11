"""A ``successful_payment`` service message must ALWAYS reach its handler.

Telegram charges the user the instant it delivers ``successful_payment`` (the
pre_checkout_query was already answered ``ok=True``). If the ban / maintenance /
channel-gate middleware drops that message because the user's state changed in
the seconds between pre-checkout and delivery — got banned, maintenance toggled
on, unsubscribed from the gated channel — the money is taken but the credits are
never applied. The throttling middleware already carves this out; these three
must mirror it. (Phase-6 audit finding P2.)
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest_asyncio

from bot.middlewares.ban import BanMiddleware
from bot.middlewares.gate import ChannelGateMiddleware
from bot.middlewares.maintenance import MaintenanceMiddleware
from core.db import SessionFactory, engine
from core.models import Base, User
from core.services import feature_flags, pricing


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


class _PaymentMsg:
    """Duck-typed successful_payment carrier — not a Message/CallbackQuery, so if the
    carve-out is missing the middleware just drops it (handler never runs)."""

    def __init__(self) -> None:
        self.successful_payment = SimpleNamespace(invoice_payload="sub:premium:1")
        self.language_code = "ru"

    async def answer(self, *a, **k):  # never expected to be called on the pay path
        raise AssertionError("payment message must not be answered/blocked")


async def _handler_flag():
    calls = {"handled": False}

    async def handler(event, data):
        calls["handled"] = True
        return "ok"

    return calls, handler


async def test_ban_lets_successful_payment_through():
    calls, handler = await _handler_flag()
    banned = SimpleNamespace(user_id=1, is_banned=True, language_code="ru")
    out = await BanMiddleware()(handler, _PaymentMsg(), {"user": banned})
    assert calls["handled"] is True and out == "ok"


async def test_maintenance_lets_successful_payment_through():
    async with SessionFactory() as s:
        u = User(user_id=2, username="u", language_code="ru")
        s.add(u)
        await s.commit()
        await pricing.set_config(s, {"maintenance": {"enabled": True, "message": "stop"}})

        calls, handler = await _handler_flag()
        out = await MaintenanceMiddleware()(
            handler, _PaymentMsg(), {"user": u, "session": s}
        )
        assert calls["handled"] is True and out == "ok"


async def test_gate_lets_successful_payment_through():
    async with SessionFactory() as s:
        u = User(user_id=3, username="u", language_code="ru")
        s.add(u)
        await s.commit()
        await feature_flags.set_flag(s, "channel_gate", True)

        calls, handler = await _handler_flag()
        out = await ChannelGateMiddleware()(
            handler, _PaymentMsg(), {"user": u, "session": s}
        )
        assert calls["handled"] is True and out == "ok"
