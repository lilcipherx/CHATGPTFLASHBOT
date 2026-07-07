"""Admin AI-routing endpoints — test-connection + import/export (ТЗ §2).

Calls the endpoint coroutines directly against a real SQLite DB (same pattern as
tests/test_business_admin). _account_ping is monkeypatched so no network is hit.
"""
from __future__ import annotations

import ipaddress
import types

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from api.admin import ai_routing
from core.db import SessionFactory, engine
from core.models import AdminAuditLog, AdminUser, Base
from core.models.ai_routing import AIAccount, AIModel
from core.services.admin_auth import hash_password
from core.services.crypto import decrypt


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture(autouse=True)
def _resolvable_hosts(monkeypatch):
    # FIX: AUDIT-TEST - the SSRF guard resolves base_url hosts via DNS and (FIX: N6)
    # fails CLOSED on an unresolvable host. These tests use example hosts (gw.example)
    # that don't resolve, esp. offline, so stub the resolver to a PUBLIC IP → the
    # allow-path is exercised without network. SSRF *rejection* is covered by
    # tests/test_security_hardening (literal internal IPs / resolves-to-loopback).
    monkeypatch.setattr(
        ai_routing, "_resolve_host_candidates",
        lambda host: [ipaddress.ip_address("93.184.216.34")],
    )


def _req():
    return types.SimpleNamespace(client=None)


async def _admin(session, role="superadmin") -> AdminUser:
    a = AdminUser(email="r@x.io", password_hash=hash_password("x"), role=role, is_active=True)
    session.add(a)
    await session.commit()
    return a


async def _seed_account(session, **kw) -> AIAccount:
    from core.services.crypto import encrypt

    defaults = dict(name="acc", kind="omniroute", base_url="https://gw.example/v1",
                    api_key=encrypt("sk-secret-1234"), modality="text", tier=0, priority=100)
    defaults.update(kw)
    acc = AIAccount(**defaults)
    session.add(acc)
    await session.commit()
    return acc


async def test_test_account_ok(monkeypatch):
    captured = {}

    async def fake_ping(base_url, api_key):
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        return {"ok": True, "status_code": 200, "latency_ms": 42, "detail": ""}

    monkeypatch.setattr(ai_routing, "_account_ping", fake_ping)
    async with SessionFactory() as s:
        a = await _admin(s)
        acc = await _seed_account(s)
        out = await ai_routing.test_account(acc.id, _req(), admin=a, session=s)
        assert out["ok"] is True and out["latency_ms"] == 42
        # the DECRYPTED key is what gets probed (not the ciphertext)
        assert captured["api_key"] == "sk-secret-1234"
        assert captured["base_url"] == "https://gw.example/v1"

        # a manual test must NOT trip health counters, but is audited
        await s.refresh(acc)
        assert acc.total_requests == 0 and acc.total_errors == 0
        n = await s.scalar(
            select(func.count()).select_from(AdminAuditLog)
            .where(AdminAuditLog.action == "ai.account.test")
        )
        assert n == 1


async def test_test_account_unreachable_reports_detail(monkeypatch):
    async def fake_ping(base_url, api_key):
        return {"ok": False, "status_code": 0, "latency_ms": 10, "detail": "boom"}

    monkeypatch.setattr(ai_routing, "_account_ping", fake_ping)
    async with SessionFactory() as s:
        a = await _admin(s)
        acc = await _seed_account(s)
        out = await ai_routing.test_account(acc.id, _req(), admin=a, session=s)
        assert out["ok"] is False and out["detail"] == "boom"


async def test_export_omits_keys():
    async with SessionFactory() as s:
        a = await _admin(s)
        await _seed_account(s, name="omni1")
        s.add(AIModel(key="m1", title="M1", upstream_model="vendor/m1", modality="text", cost=2))
        await s.commit()
        out = await ai_routing.export_config(admin=a, session=s)
        assert out["version"] == 1
        assert out["accounts"][0]["name"] == "omni1"
        assert "api_key" not in out["accounts"][0]  # secrets never leave
        assert out["models"][0]["key"] == "m1" and out["models"][0]["cost"] == 2


async def test_import_upserts_models_and_keyed_accounts():
    async with SessionFactory() as s:
        a = await _admin(s)
        body = ai_routing.ImportConfig(
            models=[{"key": "m1", "title": "M1", "upstream_model": "vendor/m1",
                     "modality": "text", "cost": 3}],
            accounts=[
                {"name": "new1", "kind": "omniroute", "base_url": "https://gw.example/v1",
                 "modality": "text", "tier": 0, "priority": 5, "api_key": "sk-fresh-9999"},
                {"name": "nokey", "base_url": "https://gw.example/v1",
                 "modality": "text"},  # no api_key -> skipped
            ],
        )
        out = await ai_routing.import_config(body, _req(), admin=a, session=s)
        assert out["models"] == 1 and out["accounts"] == 1  # keyless account skipped

        m = await s.get(AIModel, "m1")
        assert m is not None and m.cost == 3
        acc = (await s.scalars(
            select(AIAccount).where(AIAccount.name == "new1")
        )).first()
        assert acc is not None and decrypt(acc.api_key) == "sk-fresh-9999"
        assert (await s.scalars(
            select(AIAccount).where(AIAccount.name == "nokey")
        )).first() is None


async def test_import_updates_existing_account_without_clobbering_key():
    from core.services.crypto import encrypt

    async with SessionFactory() as s:
        a = await _admin(s)
        s.add(AIAccount(name="ex", kind="omniroute", base_url="https://old/v1",
                        api_key=encrypt("sk-keep-me"), modality="text", tier=0, priority=100))
        await s.commit()

        body = ai_routing.ImportConfig(accounts=[
            {"name": "ex", "kind": "openrouter", "base_url": "https://new/v1",
             "modality": "text", "tier": 1, "priority": 7},  # no api_key
        ])
        await ai_routing.import_config(body, _req(), admin=a, session=s)

        acc = (await s.scalars(
            select(AIAccount).where(AIAccount.name == "ex")
        )).first()
        assert acc.base_url == "https://new/v1" and acc.tier == 1 and acc.priority == 7
        assert decrypt(acc.api_key) == "sk-keep-me"  # existing key preserved


async def test_strategy_get_set_roundtrip_and_validation():
    from fastapi import HTTPException

    async with SessionFactory() as s:
        admin = await _admin(s, "admin")
        out = await ai_routing.get_routing_strategy(admin=admin, session=s)
        assert out["strategy"] == "weighted" and "round_robin" in out["options"]

        await ai_routing.set_routing_strategy(
            ai_routing.StrategyReq(strategy="least_latency"), _req(), admin=admin, session=s)
        out2 = await ai_routing.get_routing_strategy(admin=admin, session=s)
        assert out2["strategy"] == "least_latency"

        with pytest.raises(HTTPException) as ei:
            await ai_routing.set_routing_strategy(
                ai_routing.StrategyReq(strategy="bogus"), _req(), admin=admin, session=s)
        assert ei.value.status_code == 400


async def test_model_upsert_persists_token_pricing():
    async with SessionFactory() as s:
        admin = await _admin(s, "superadmin")
        await ai_routing.upsert_model(
            "gpt", ai_routing.ModelUpsert(title="GPT", upstream_model="gpt-x",
                                          price_in_micros=3_000_000, price_out_micros=15_000_000),
            _req(), admin=admin, session=s)
        rows = await ai_routing.list_models(admin=admin, session=s)
    m = next(r for r in rows if r["key"] == "gpt")
    assert m["price_in_micros"] == 3_000_000 and m["price_out_micros"] == 15_000_000


async def test_router_panels_defaults_set_and_sanitize():
    async with SessionFactory() as s:
        admin = await _admin(s, "admin")
        # defaults when unset: OmniRoute with an empty URL (LiteLLM removed AUDIT13)
        out = await ai_routing.get_router_panels(admin=admin, session=s)
        names = {p["name"] for p in out["panels"]}
        assert {"OmniRoute"} <= names

        # save: valid http URL kept, javascript: scheme stripped, no-name dropped
        await ai_routing.set_router_panels(
            ai_routing.RouterPanelsReq(panels=[
                {"name": "LiteLLM", "url": "http://localhost:4000/ui"},
                {"name": "Bad", "url": "javascript:alert(1)"},
                {"name": "", "url": "http://x"},
            ]), _req(), admin=admin, session=s)
        out2 = await ai_routing.get_router_panels(admin=admin, session=s)
    by_name = {p["name"]: p["url"] for p in out2["panels"]}
    # no-name dropped, js stripped
    assert by_name == {"LiteLLM": "http://localhost:4000/ui", "Bad": ""}
