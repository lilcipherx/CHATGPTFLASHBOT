"""White-label bots admin endpoints — enriched serializer + per-bot stats.

Calls the endpoint coroutines directly against a seeded SQLite schema (no HTTP),
mirroring tests/test_multibot.py. Covers the two additions behind the reworked
«Боты (White Label)» page:
  * GET /bots now exposes created_at / updated_at (no migration).
  * GET /bots/stats returns real per-bot engagement (users + generation jobs +
    last activity) via User.bot_id attribution, with a "legacy" bucket for the
    NULL-bot_id primary users.
"""
from __future__ import annotations

import types

import pytest
import pytest_asyncio
from fastapi import HTTPException

from api.admin import bots as bots_api
from api.admin.bots import bots_stats, list_bots
from core.db import SessionFactory, engine
from core.models import AdminUser, Base, GenerationJob
from core.services import bots as bots_svc
from core.services.users import get_or_create_user


def _req():
    return types.SimpleNamespace(client=None)


# Well-formed-looking tokens (digits:≥30 chars) so format checks pass.
TOK_A = "123456:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
TOK_B = "654321:BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    bots_svc.clear_map()
    yield


async def _admin() -> AdminUser:
    async with SessionFactory() as s:
        a = AdminUser(email="root@x.io", password_hash="x", role="superadmin")
        s.add(a)
        await s.commit()
        await s.refresh(a)
        return a


async def _jobs(session, user_id: int, n: int) -> None:
    for _ in range(n):
        session.add(GenerationJob(user_id=user_id, service="chat"))
    await session.commit()


async def test_list_exposes_timestamps():
    admin = await _admin()
    async with SessionFactory() as s:
        await bots_svc.create_bot(s, title="Brand A", token="123456:tokAAAA")
    async with SessionFactory() as s:
        out = await list_bots(admin=admin, session=s)
    assert len(out) == 1
    row = out[0]
    assert row["created_at"] is not None
    assert row["updated_at"] is not None
    # masked token only — never the raw secret
    assert "tokAAAA" not in row["token_masked"]


async def test_stats_per_bot_and_legacy_bucket():
    admin = await _admin()
    async with SessionFactory() as s:
        a = await bots_svc.create_bot(s, title="A", token="1:aaaaaaaaaaaa", is_default=True)
        b = await bots_svc.create_bot(s, title="B", token="2:bbbbbbbbbbbb")

    async with SessionFactory() as s:
        # 2 users on bot A (3 jobs), 1 on bot B (1 job), 1 legacy/NULL (2 jobs)
        u1, _ = await get_or_create_user(s, 101, bot_id=a.id)
        u2, _ = await get_or_create_user(s, 102, bot_id=a.id)
        u3, _ = await get_or_create_user(s, 201, bot_id=b.id)
        u4, _ = await get_or_create_user(s, 301, bot_id=None)
        await _jobs(s, u1.user_id, 2)
        await _jobs(s, u2.user_id, 1)
        await _jobs(s, u3.user_id, 1)
        await _jobs(s, u4.user_id, 2)

    async with SessionFactory() as s:
        out = await bots_stats(admin=admin, session=s)

    stats = out["stats"]
    assert stats[str(a.id)]["users"] == 2
    assert stats[str(a.id)]["requests"] == 3
    assert stats[str(b.id)]["users"] == 1
    assert stats[str(b.id)]["requests"] == 1
    # NULL bot_id users land in the "legacy" bucket
    assert stats["legacy"]["users"] == 1
    assert stats["legacy"]["requests"] == 2
    # per-bot last activity is populated
    assert stats[str(a.id)]["last_request_at"] is not None
    # totals sum everything
    assert out["totals"]["users"] == 4
    assert out["totals"]["requests"] == 6


async def test_stats_empty_when_no_users():
    admin = await _admin()
    async with SessionFactory() as s:
        await bots_svc.create_bot(s, title="Solo", token="9:cccccccccccc")
    async with SessionFactory() as s:
        out = await bots_stats(admin=admin, session=s)
    assert out["stats"] == {}
    assert out["totals"] == {"users": 0, "requests": 0}


# ---- hardening: duplicate-token + default-bot protection + getMe probe ----

async def test_create_rejects_duplicate_token():
    admin = await _admin()
    async with SessionFactory() as s:
        await bots_api.create_bot(bots_api.BotCreate(title="One", token=TOK_A), _req(), admin, s)
        with pytest.raises(HTTPException) as ei:
            await bots_api.create_bot(
                bots_api.BotCreate(title="Two", token=TOK_A), _req(), admin, s)
        assert ei.value.status_code == 400
        assert "токен" in ei.value.detail.lower()


async def test_token_in_use_helper_excludes_self():
    async with SessionFactory() as s:
        b = await bots_svc.create_bot(s, title="One", token=TOK_A)
        assert await bots_svc.token_in_use(s, TOK_A) is True
        assert await bots_svc.token_in_use(s, TOK_A, exclude_id=b.id) is False
        assert await bots_svc.token_in_use(s, TOK_B) is False


async def test_cannot_delete_default_bot():
    admin = await _admin()
    async with SessionFactory() as s:
        b = await bots_svc.create_bot(s, title="Main", token=TOK_A, is_default=True)
        with pytest.raises(HTTPException) as ei:
            await bots_api.delete_bot(b.id, _req(), admin, s)
        assert ei.value.status_code == 400
        b2 = await bots_svc.create_bot(s, title="Side", token=TOK_B)
        assert await bots_api.delete_bot(b2.id, _req(), admin, s) == {"ok": True}


async def test_cannot_disable_default_bot():
    admin = await _admin()
    async with SessionFactory() as s:
        b = await bots_svc.create_bot(s, title="Main", token=TOK_A, is_default=True)
        with pytest.raises(HTTPException) as ei:
            await bots_api.update_bot(b.id, bots_api.BotUpdate(active=False), _req(), admin, s)
        assert ei.value.status_code == 400


async def test_update_rejects_duplicate_token():
    admin = await _admin()
    async with SessionFactory() as s:
        await bots_svc.create_bot(s, title="One", token=TOK_A)
        b2 = await bots_svc.create_bot(s, title="Two", token=TOK_B)
        with pytest.raises(HTTPException) as ei:
            await bots_api.update_bot(b2.id, bots_api.BotUpdate(token=TOK_A), _req(), admin, s)
        assert ei.value.status_code == 400


async def test_check_token_endpoint(monkeypatch):
    async def _fake_verify(token):
        return {"ok": True, "tg_bot_id": 777, "username": "demo_bot", "name": "Demo",
                "status_code": 200, "latency_ms": 42, "detail": ""}
    monkeypatch.setattr(bots_svc, "verify_token", _fake_verify)
    admin = await _admin()
    out = await bots_api.check_token(bots_api.TokenCheck(token=TOK_A), admin)
    assert out["ok"] is True and out["username"] == "demo_bot"


async def test_check_existing_bot_uses_stored_token(monkeypatch):
    seen = {}

    async def _fake_verify(token):
        seen["token"] = token
        return {"ok": True, "tg_bot_id": 1, "username": "u", "name": "n",
                "status_code": 200, "latency_ms": 1, "detail": ""}
    monkeypatch.setattr(bots_svc, "verify_token", _fake_verify)
    admin = await _admin()
    async with SessionFactory() as s:
        b = await bots_svc.create_bot(s, title="One", token=TOK_A)
        out = await bots_api.check_bot(b.id, admin, s)
    assert out["ok"] is True
    assert seen["token"] == TOK_A  # decrypted back to original plaintext


async def test_verify_token_rejects_bad_format():
    res = await bots_svc.verify_token("not-a-token")
    assert res["ok"] is False and res["tg_bot_id"] is None
