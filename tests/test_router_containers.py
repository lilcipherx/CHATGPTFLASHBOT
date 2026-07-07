"""Router-container management (ТЗ §2): allowlist + feature-flag guards, argv
construction, and tail clamping — all without a real docker daemon (``_run`` stubbed).
"""
from __future__ import annotations

import types

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select

from api.admin import router_containers as ep
from core.config import settings
from core.db import SessionFactory, engine
from core.models import AdminAuditLog, AdminUser, Base
from core.services import router_containers as rc
from core.services.admin_auth import hash_password


@pytest.fixture
def captured(monkeypatch):
    """Stub the single subprocess boundary; record the argv each call would run."""
    calls: list[list[str]] = []

    async def _fake_run(args: list[str]) -> rc.CmdResult:
        calls.append(args)
        return rc.CmdResult(True, 0, "ok", "")

    monkeypatch.setattr(rc, "_run", _fake_run)
    return calls


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "router_mgmt_enabled", True)


async def test_disabled_by_default_blocks_every_op(monkeypatch, captured):
    monkeypatch.setattr(settings, "router_mgmt_enabled", False)
    assert rc.is_enabled() is False
    for op in (
        rc.status("litellm"),
        rc.action("litellm", "restart"),
        rc.logs("litellm"),
    ):
        with pytest.raises(rc.RouterMgmtDisabled):
            await op
    assert captured == []  # nothing ever shelled out


async def test_unknown_service_is_rejected(enabled, captured):
    for op in (
        rc.status("postgres"),       # real service, but NOT a router → blocked
        rc.action("redis", "stop"),
        rc.logs("../etc/passwd"),
    ):
        with pytest.raises(rc.UnknownRouter):
            await op
    assert captured == []


async def test_status_and_actions_build_expected_argv(enabled, captured):
    await rc.status("litellm")
    await rc.action("litellm", "start")
    await rc.action("litellm", "stop")
    await rc.action("litellm", "restart")
    assert captured == [
        ["ps", "litellm"],
        ["start", "litellm"],
        ["stop", "litellm"],
        ["restart", "litellm"],
    ]


async def test_bad_verb_rejected(enabled, captured):
    with pytest.raises(ValueError):
        await rc.action("litellm", "exec")     # not in ACTIONS
    assert captured == []


async def test_logs_tail_is_clamped(enabled, captured):
    await rc.logs("litellm", tail=10)
    await rc.logs("litellm", tail=10_000)      # over ceiling
    await rc.logs("litellm", tail=0)           # under floor
    assert captured == [
        ["logs", "--no-color", "--tail", "10", "litellm"],
        ["logs", "--no-color", "--tail", str(rc._LOGS_MAX_TAIL), "litellm"],
        ["logs", "--no-color", "--tail", "1", "litellm"],
    ]


# --------------------------------------------------------------------------- #
# endpoint layer (HTTP translation + audit), coroutines called directly
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req():
    return types.SimpleNamespace(client=None)


async def _admin(session):
    a = AdminUser(email="r@x.io", password_hash=hash_password("x"),
                  role="superadmin", is_active=True)
    session.add(a)
    await session.commit()
    return a


async def test_endpoint_action_succeeds_and_audits(enabled, captured, _schema):
    async with SessionFactory() as s:
        admin = await _admin(s)
        out = await ep.router_action("litellm", "restart", _req(), admin=admin, session=s)
        assert out["ok"] is True
        assert captured == [["restart", "litellm"]]
        n = await s.scalar(
            select(func.count()).select_from(AdminAuditLog)
            .where(AdminAuditLog.action == "router.restart")
        )
        assert n == 1


async def test_endpoint_unknown_action_is_404(enabled, captured, _schema):
    async with SessionFactory() as s:
        admin = await _admin(s)
        with pytest.raises(HTTPException) as ei:
            await ep.router_action("litellm", "exec", _req(), admin=admin, session=s)
        assert ei.value.status_code == 404
        assert captured == []  # never reached the service


async def test_endpoint_disabled_is_403(monkeypatch, captured, _schema):
    monkeypatch.setattr(settings, "router_mgmt_enabled", False)
    async with SessionFactory() as s:
        admin = await _admin(s)
        with pytest.raises(HTTPException) as ei:
            await ep.router_status("litellm", admin=admin, session=s)
        assert ei.value.status_code == 403


async def test_endpoint_unknown_service_is_404(enabled, captured, _schema):
    async with SessionFactory() as s:
        admin = await _admin(s)
        with pytest.raises(HTTPException) as ei:
            await ep.router_status("postgres", admin=admin, session=s)
        assert ei.value.status_code == 404
