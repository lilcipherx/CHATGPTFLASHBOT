"""Regression tests for the post-audit hardening pass:

* #1 Mini App effect generation MUST moderate the user prompt (parity with the bot).
* #2 admin AI-account base_url is SSRF-validated (scheme + private-IP / allowlist).
* #3 a transient payment-webhook verify failure returns 5xx (gateway retries),
     while a definitive rejection returns 200 (no retry).
* #4 config fails closed on insecure secrets when a public webhook deploy is set,
     even if ENV was left at dev/test.
"""
from __future__ import annotations

import types

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.responses import Response

from core.db import SessionFactory, engine
from core.models import Base, MiniAppPhotoEffect, User


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


# ---------- #1 Mini App moderation parity ----------
async def test_effect_generate_blocks_moderated_prompt(monkeypatch):
    from core.services import moderation
    from core.services.moderation import ModerationResult

    async def _blocked(_text: str) -> ModerationResult:
        return ModerationResult(False, "test")

    monkeypatch.setattr(moderation, "moderate", _blocked)

    from api.routers import miniapp

    async with SessionFactory() as s:
        s.add(User(user_id=1, language_code="ru", credits=100))
        eff = MiniAppPhotoEffect(
            name_ru="Test", category="all", enabled=True,
            recommended_model="nano_banana", max_photos=1,
        )
        s.add(eff)
        await s.commit()
        eid = eff.effect_id

    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await miniapp.effect_generate(
                kind="photo", effect_id=eid, model="nano_banana",
                params="{}", prompt="forbidden text", photos=[],
                tg={"id": 1, "username": "u", "language_code": "ru"}, session=s,
            )
        assert ei.value.status_code == 400

    # the blocked request must NOT have charged the user or created a job
    async with SessionFactory() as s:
        u = await s.get(User, 1)
        assert u.credits == 100
        from sqlalchemy import func, select

        from core.models import GenerationJob

        jobs = await s.scalar(select(func.count()).select_from(GenerationJob))
        assert jobs == 0


# ---------- #2 SSRF base_url validation ----------
def test_validate_base_url_accepts_public_https():
    from api.admin.ai_routing import _validate_base_url

    assert _validate_base_url("https://api.openai.com/v1/") == "https://api.openai.com/v1"


@pytest.mark.parametrize("bad", [
    "ftp://api.openai.com",          # wrong scheme
    "not-a-url",                     # no host
    "http://127.0.0.1:8000",         # loopback
    "http://169.254.169.254/latest", # cloud metadata
    "http://10.0.0.5",               # private
])
def test_validate_base_url_rejects_ssrf(bad):
    from api.admin.ai_routing import _validate_base_url

    with pytest.raises(HTTPException) as ei:
        _validate_base_url(bad)
    assert ei.value.status_code == 400


def test_validate_base_url_allowlist(monkeypatch):
    from api.admin import ai_routing

    # With an allowlist, an internal host is permitted and others rejected.
    monkeypatch.setattr(
        type(ai_routing.settings), "ai_base_url_allow",
        property(lambda self: ["omniroute"]),
    )
    assert ai_routing._validate_base_url("http://omniroute:20128") == "http://omniroute:20128"
    with pytest.raises(HTTPException):
        ai_routing._validate_base_url("https://evil.example.com")


# ---------- #3 webhook transient vs forgery ----------
class _FakeReq:
    client = types.SimpleNamespace(host="1.2.3.4")
    headers: dict = {}

    async def body(self) -> bytes:
        return b"{}"


async def test_webhook_retryable_returns_503(monkeypatch):
    from core.payments import PaymentRetryable

    class _Prov:
        def verify_webhook(self, headers, body):
            raise PaymentRetryable("re-fetch timed out")

    from api.routers import webhooks

    monkeypatch.setattr(webhooks, "get_provider", lambda g: _Prov())
    out = await webhooks._handle_gateway("stripe", _FakeReq())
    assert isinstance(out, Response) and out.status_code == 503


async def test_webhook_forgery_acks_200(monkeypatch):
    from core.payments import PaymentError

    class _Prov:
        def verify_webhook(self, headers, body):
            raise PaymentError("bad signature")

    from api.routers import webhooks

    monkeypatch.setattr(webhooks, "get_provider", lambda g: _Prov())
    out = await webhooks._handle_gateway("stripe", _FakeReq())
    assert out == {"ok": False, "error": "invalid signature"}


# ---------- #4 config fail-closed on public deploy ----------
def test_config_fails_closed_on_public_webhook():
    from core.config import Settings

    s = Settings(
        env="dev", bot_mode="webhook", webhook_base_url="https://bot.example.com",
        admin_jwt_secret="change-me-in-prod",
    )
    assert s.is_public_deploy is True
    with pytest.raises(RuntimeError):
        s._require_prod_secret()


def test_config_dev_polling_is_lenient():
    from core.config import Settings

    s = Settings(env="dev", bot_mode="polling", admin_jwt_secret="change-me-in-prod")
    assert s.is_public_deploy is False
    s._require_prod_secret()  # must not raise
