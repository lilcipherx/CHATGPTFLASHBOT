"""Reworked «Безопасность» page — the Security Center posture endpoint (no
migration): GET /auth/security returns the current admin's account, org-wide
AdminUser aggregates, the deploy's auth policy, recent security audit events, and a
weighted score + recommendations.

Calls the endpoint coroutine directly against a seeded SQLite DB.
"""
from __future__ import annotations

import pytest_asyncio

from api.admin import auth
from core.db import SessionFactory, engine
from core.models import AdminAuditLog, AdminUser, Base
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _mk(session, *, email, role, twofa=False, active=True) -> AdminUser:
    a = AdminUser(email=email, password_hash=hash_password("x"), role=role,
                  is_active=active, totp_secret="S" * 16 if twofa else None)
    session.add(a)
    await session.commit()
    await session.refresh(a)
    return a


async def test_overview_structure_and_org_aggregates():
    async with SessionFactory() as s:
        me = await _mk(s, email="root@x.io", role="superadmin", twofa=True)
        await _mk(s, email="a1@x.io", role="admin", twofa=True)
        await _mk(s, email="a2@x.io", role="admin", twofa=False)   # required-role, no 2FA
        await _mk(s, email="sup@x.io", role="support", twofa=False)
        s.add(AdminAuditLog(admin_id=me.id, action="admin.create",
                            target_type="admin", target_id="a2@x.io", ip="1.1.1.1"))
        await s.commit()

    async with SessionFactory() as s:
        me = await s.get(AdminUser, me.id)
        out = await auth.security_overview(admin=me, session=s)

    assert out["self"]["role"] == "superadmin"
    assert out["self"]["has_2fa"] is True
    assert out["self"]["role_rank"] == 4

    org = out["org"]
    assert org["admins_total"] == 4
    assert org["with_2fa"] == 2
    assert org["without_2fa"] == 2
    assert org["by_role"]["admin"] == 2
    # default mfa_required_roles = admin,superadmin → a2 (admin, no 2FA) is missing.
    assert org["missing_required_2fa"] == 1

    # security events feed picks up admin.* actions.
    assert any(e["action"] == "admin.create" for e in out["events"])
    assert out["last_security_event_at"] is not None
    assert out["events"][0]["admin_email"] == "root@x.io"


async def test_score_weights_and_recommendations():
    # Every required-role admin has 2FA AND self has 2FA → the two 2FA checks pass.
    async with SessionFactory() as s:
        me = await _mk(s, email="root@x.io", role="superadmin", twofa=True)
        await _mk(s, email="a1@x.io", role="admin", twofa=True)

    async with SessionFactory() as s:
        me = await s.get(AdminUser, me.id)
        out = await auth.security_overview(admin=me, session=s)

    # In the dev test env: jwt secret is default, no enc secret, no ip allowlist,
    # cookies not secure → only self_2fa (25) + org_2fa (20) pass.
    assert out["score"] == 45
    rec_ids = {r["id"] for r in out["recommendations"]}
    assert "ip_allowlist" in rec_ids
    assert "enc_secret" in rec_ids
    assert "jwt_secret" in rec_ids
    assert "self_2fa" not in rec_ids   # passed → not recommended
    # checks expose every signal with weights.
    assert {c["id"] for c in out["checks"]} == {
        "self_2fa", "org_2fa", "jwt_secret", "enc_secret", "ip_allowlist", "secure_cookies"}


async def test_self_missing_2fa_recommended():
    async with SessionFactory() as s:
        me = await _mk(s, email="root@x.io", role="admin", twofa=False)
    async with SessionFactory() as s:
        me = await s.get(AdminUser, me.id)
        out = await auth.security_overview(admin=me, session=s)
    assert out["self"]["has_2fa"] is False
    assert out["self"]["mfa_required"] is True
    assert any(r["id"] == "self_2fa" for r in out["recommendations"])


# ---- self-service password change (POST /auth/password) --------------------
import types  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException, Response  # noqa: E402
from sqlalchemy import select  # noqa: E402

from core.services.admin_auth import verify_password  # noqa: E402


def _req(ip: str = "1.2.3.4"):
    return types.SimpleNamespace(client=types.SimpleNamespace(host=ip), headers={})


async def _mk_pw(session, password: str, email="pw@x.io", role="admin") -> AdminUser:
    a = AdminUser(email=email, password_hash=hash_password(password), role=role,
                  is_active=True)
    session.add(a)
    await session.commit()
    await session.refresh(a)
    return a


async def test_change_password_success_rehashes_and_revokes():
    async with SessionFactory() as s:
        me = await _mk_pw(s, "oldpass12")
        before_tv = me.token_version
        out = await auth.change_password(
            auth.PasswordChange(current_password="oldpass12", new_password="newpass34"),
            Response(), _req(), admin=me, session=s)
        assert out == {"ok": True, "relogin_required": True}
    async with SessionFactory() as s:
        me2 = await s.get(AdminUser, me.id)
        assert verify_password("newpass34", me2.password_hash)
        assert not verify_password("oldpass12", me2.password_hash)
        assert me2.token_version == before_tv + 1  # all sessions revoked
        rows = (await s.scalars(
            select(AdminAuditLog).where(AdminAuditLog.action == "auth.password_change")
        )).all()
        assert len(rows) == 1 and rows[0].target_id == str(me.id)


async def test_change_password_wrong_current_400():
    async with SessionFactory() as s:
        me = await _mk_pw(s, "oldpass12")
        with pytest.raises(HTTPException) as ei:
            await auth.change_password(
                auth.PasswordChange(current_password="WRONGPASS", new_password="newpass34"),
                Response(), _req(), admin=me, session=s)
        assert ei.value.status_code == 400


async def test_change_password_too_short_400():
    async with SessionFactory() as s:
        me = await _mk_pw(s, "oldpass12")
        with pytest.raises(HTTPException) as ei:
            await auth.change_password(
                auth.PasswordChange(current_password="oldpass12", new_password="short"),
                Response(), _req(), admin=me, session=s)
        assert ei.value.status_code == 400


async def test_change_password_same_as_current_400():
    async with SessionFactory() as s:
        me = await _mk_pw(s, "oldpass12")
        with pytest.raises(HTTPException) as ei:
            await auth.change_password(
                auth.PasswordChange(current_password="oldpass12", new_password="oldpass12"),
                Response(), _req(), admin=me, session=s)
        assert ei.value.status_code == 400
