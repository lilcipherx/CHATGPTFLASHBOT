"""Payment-gateway credential service (core.services.gateway_keys): admin-editable
secrets stored encrypted in the pricing KV table and applied onto live settings."""
from __future__ import annotations

import pytest_asyncio

from core.config import settings
from core.db import SessionFactory, engine
from core.models import Base
from core.services import gateway_keys


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    # set_fields/clear_field mutate the GLOBAL settings object; snapshot the gateway
    # fields and restore them after each test so the change doesn't leak into other
    # suites (e.g. test_payments asserts gateways are unavailable without keys).
    snapshot = {f: getattr(settings, f, None) for f in gateway_keys._ENV_DEFAULTS}
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    for field, value in snapshot.items():
        setattr(settings, field, value)
    await engine.dispose()


async def test_status_lists_all_gateways():
    async with SessionFactory() as s:
        out = await gateway_keys.get_status(s)
    assert [g["id"] for g in out] == ["stripe", "yookassa", "crypto", "tribute"]
    stripe = out[0]
    assert [f["field"] for f in stripe["fields"]] == ["stripe_secret", "stripe_webhook_secret"]
    assert stripe["ready"] is False                  # nothing configured yet


async def test_set_secret_encrypted_and_applied_masked():
    async with SessionFactory() as s:
        changed = await gateway_keys.set_fields(s, {"stripe_secret": "sk_live_ABCD1234"})
        assert changed == ["stripe_secret"]
        # applied onto live settings (so the Stripe adapter uses it at call time)
        assert settings.stripe_secret == "sk_live_ABCD1234"
        # raw stored value is ENCRYPTED (not the plaintext)
        raw = await gateway_keys._load_raw(s)
        assert raw["stripe_secret"] != "sk_live_ABCD1234"

        out = await gateway_keys.get_status(s)
        f = out[0]["fields"][0]
        assert f["configured"] and f["source"] == "db"
        assert f["value"] == "…1234" and "sk_live" not in f["value"]   # masked


async def test_non_secret_field_stored_plaintext_and_visible():
    async with SessionFactory() as s:
        await gateway_keys.set_fields(s, {"yookassa_shop_id": "shop-42"})
        raw = await gateway_keys._load_raw(s)
        assert raw["yookassa_shop_id"] == "shop-42"          # plaintext (not a secret)
        out = await gateway_keys.get_status(s)
        yk = next(g for g in out if g["id"] == "yookassa")
        shop = yk["fields"][0]
        assert shop["secret"] is False and shop["value"] == "shop-42"   # shown in full


async def test_clear_reverts_to_env_default():
    async with SessionFactory() as s:
        await gateway_keys.set_fields(s, {"crypto_pay_token": "tok_123456"})
        assert settings.crypto_pay_token == "tok_123456"
        existed = await gateway_keys.clear_field(s, "crypto_pay_token")
        assert existed is True
        # reverted to the .env snapshot taken at import
        assert settings.crypto_pay_token == gateway_keys._ENV_DEFAULTS["crypto_pay_token"]
        out = await gateway_keys.get_status(s)
        ct = next(g for g in out if g["id"] == "crypto")["fields"][0]
        assert ct["source"] in ("env", "none")


async def test_empty_value_ignored():
    async with SessionFactory() as s:
        changed = await gateway_keys.set_fields(s, {"tribute_api_key": "   "})
        assert changed == []
