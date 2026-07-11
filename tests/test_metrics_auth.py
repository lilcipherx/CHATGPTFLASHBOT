"""/metrics endpoint auth (AUDIT-A2).

The Prometheus /metrics endpoint exposes total/premium/banned user counts and job
stats. It must fail closed (require METRICS_TOKEN) on any non-local deploy — including
a prod bot running in POLLING mode, where is_public_deploy is False because no
WEBHOOK_BASE_URL is set. Only a local dev/test box may serve it unauthenticated.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.routers.health import metrics
from core.config import settings
from core.db import SessionFactory, engine
from core.models import Base


@pytest.fixture(autouse=True)
def _polling_no_token(monkeypatch):
    # Polling deploy: no PUBLIC_DEPLOY, no WEBHOOK_BASE_URL → is_public_deploy False.
    monkeypatch.setattr(settings, "public_deploy", False)
    monkeypatch.setattr(settings, "webhook_base_url", "")
    monkeypatch.setattr(settings, "metrics_token", "")


import pytest_asyncio  # noqa: E402


@pytest_asyncio.fixture
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_metrics_requires_token_in_prod_polling(monkeypatch, _schema):
    monkeypatch.setattr(settings, "env", "prod")
    assert settings.is_public_deploy is False  # polling prod is still internet-reachable
    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await metrics(token="", x_metrics_token="", session=s)
        assert ei.value.status_code == 403


async def test_metrics_permissive_in_local_dev(monkeypatch, _schema):
    monkeypatch.setattr(settings, "env", "dev")
    assert settings.is_public_deploy is False
    async with SessionFactory() as s:
        resp = await metrics(token="", x_metrics_token="", session=s)
        assert resp.status_code == 200  # local dev/test stays permissive


async def test_metrics_accepts_bearer_header(monkeypatch, _schema):
    """Prometheus can authenticate with a standard Authorization: Bearer header so the
    token never has to sit in the scrape URL (query string → proxy/access logs)."""
    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "metrics_token", "secret-tok")
    async with SessionFactory() as s:
        resp = await metrics(
            token="", x_metrics_token="", authorization="Bearer secret-tok", session=s
        )
        assert resp.status_code == 200


async def test_metrics_rejects_wrong_bearer(monkeypatch, _schema):
    monkeypatch.setattr(settings, "env", "prod")
    monkeypatch.setattr(settings, "metrics_token", "secret-tok")
    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await metrics(
                token="", x_metrics_token="", authorization="Bearer nope", session=s
            )
        assert ei.value.status_code == 403
