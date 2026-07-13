"""Gateway webhook handler dispatch (Loop coverage, money entry point): the
_handle_gateway branches — unknown gateway, YooKassa source-IP allowlist, a transient
verify (→503 retry), a definitive bad signature (→200 reject), an ignored event, and a
verified paid event flowing into apply_event. Providers are faked; DB is real (SQLite).
"""
from __future__ import annotations

import types

import pytest_asyncio
from starlette.responses import Response

from api.routers import webhooks
from core.config import settings
from core.db import engine
from core.models import Base
from core.payments.base import PaymentError, PaymentEvent, PaymentRetryable


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


class _Req:
    def __init__(self, headers=None, body=b"{}", client_host="203.0.113.5"):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self._body = body
        self.client = types.SimpleNamespace(host=client_host)

    async def body(self):
        return self._body


def _provider(**kw):
    return types.SimpleNamespace(**kw)


async def test_unknown_gateway(monkeypatch):
    monkeypatch.setattr(webhooks, "get_provider", lambda g: None)
    res = await webhooks._handle_gateway("nope", _Req())
    assert res == {"ok": False, "error": "unknown gateway"}


async def test_verify_returns_none_is_ignored(monkeypatch):
    monkeypatch.setattr(webhooks, "get_provider",
                        lambda g: _provider(verify_webhook=lambda h, b: None))
    res = await webhooks._handle_gateway("stripe", _Req())
    assert res == {"ok": True, "ignored": True}


async def test_bad_signature_is_rejected_200(monkeypatch):
    def _verify(h, b):
        raise PaymentError("bad sig")
    monkeypatch.setattr(webhooks, "get_provider", lambda g: _provider(verify_webhook=_verify))
    res = await webhooks._handle_gateway("stripe", _Req())
    assert res == {"ok": False, "error": "invalid signature"}


async def test_transient_verify_returns_503(monkeypatch):
    def _verify(h, b):
        raise PaymentRetryable("timeout")
    monkeypatch.setattr(webhooks, "get_provider", lambda g: _provider(verify_webhook=_verify))
    res = await webhooks._handle_gateway("stripe", _Req())
    assert isinstance(res, Response) and res.status_code == 503


async def test_yookassa_ip_not_allowed(monkeypatch):
    monkeypatch.setattr(settings, "yookassa_webhook_ips", "203.0.113.0/24")
    monkeypatch.setattr(webhooks, "get_provider",
                        lambda g: _provider(verify_webhook=lambda h, b: None))
    # XFF right-most hop is outside the allowed range → rejected before verify.
    req = _Req(headers={"x-forwarded-for": "8.8.8.8"})
    res = await webhooks._handle_gateway("yookassa", req)
    assert res == {"ok": False, "error": "ip not allowed"}


async def test_verified_paid_event_unknown_user_ok(monkeypatch):
    # A signed paid event for a user we don't have → apply_event drops it, handler 200s.
    ev = PaymentEvent(payload="credits:999999:10", gateway="stripe",
                      gateway_tx_id="cs_x", amount=0, status="paid")
    monkeypatch.setattr(webhooks, "get_provider",
                        lambda g: _provider(verify_webhook=lambda h, b: ev))
    res = await webhooks._handle_gateway("stripe", _Req())
    assert res == {"ok": True}
