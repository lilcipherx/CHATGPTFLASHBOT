"""Admin-managed native provider API keys (core.services.provider_keys).

Verifies: a key set in the DB is encrypted at rest, applied onto live settings
(so adapters use it), reported masked with source=db, and reverts to the .env
default when cleared. Real SQLite, no network.
"""
from __future__ import annotations

import pytest_asyncio

from core.config import settings
from core.db import SessionFactory, engine
from core.models import Base, Pricing
from core.services import provider_keys


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_set_applies_and_masks():
    async with SessionFactory() as s:
        changed = await provider_keys.set_keys(s, {"openai": "sk-secret-1234"})
        assert changed == ["openai"]
        # Applied onto live settings so every adapter picks it up.
        assert settings.openai_api_key == "sk-secret-1234"

        # Stored value is encrypted, not plaintext.
        row = await s.get(Pricing, provider_keys.KEY)
        assert "sk-secret-1234" not in str(row.value)

        status = {r["name"]: r for r in await provider_keys.get_status(s)}
        assert status["openai"]["configured"] is True
        assert status["openai"]["source"] == "db"
        assert status["openai"]["masked"].endswith("1234")
        # An unset provider is reported but not configured (unless .env had it).
        assert status["anthropic"]["source"] in ("env", "none")


async def test_empty_value_is_ignored():
    async with SessionFactory() as s:
        await provider_keys.set_keys(s, {"openai": "sk-keepme-9999"})
        changed = await provider_keys.set_keys(s, {"openai": "   "})
        assert changed == []  # blank = keep existing
        assert settings.openai_api_key == "sk-keepme-9999"


async def test_clear_reverts_to_env_default():
    async with SessionFactory() as s:
        await provider_keys.set_keys(s, {"deepseek": "sk-db-key"})
        assert settings.deepseek_api_key == "sk-db-key"
        cleared = await provider_keys.clear_key(s, "deepseek")
        assert cleared is True
        # Reverts to the snapshotted .env default (empty in the test env).
        assert settings.deepseek_api_key == provider_keys._ENV_DEFAULTS["deepseek_api_key"]


# ---- online key test (probe the provider with the stored key) ----
async def test_test_key_no_key_and_unsupported():
    async with SessionFactory() as s:
        # no key set + .env empty in tests -> "ключ не задан"
        r = await provider_keys.test_key(s, "deepseek")
        assert r["ok"] is False and r["supported"] is True and "не задан" in r["detail"]

        # a media provider has no online-test spec -> supported False
        await provider_keys.set_keys(s, {"kling": "kk-123456789012345"})
        r2 = await provider_keys.test_key(s, "kling")
        assert r2["ok"] is False and r2["supported"] is False

        # unknown provider name
        r3 = await provider_keys.test_key(s, "nope")
        assert r3["supported"] is False


async def test_test_key_probes_with_bearer(monkeypatch):
    """A configured OpenAI-compatible key is probed via GET …/models with Bearer auth;
    a 200 means the key works."""
    captured = {}

    class _Resp:
        status_code = 200
        text = "{}"

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None, params=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    async with SessionFactory() as s:
        await provider_keys.set_keys(s, {"openrouter": "sk-or-abcdef123456"})
        r = await provider_keys.test_key(s, "openrouter")
    assert r["ok"] is True and r["status_code"] == 200 and r["supported"] is True
    assert captured["url"].endswith("/models")
    assert captured["headers"]["Authorization"] == "Bearer sk-or-abcdef123456"
