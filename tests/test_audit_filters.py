"""Audit-log filters (ТЗ §8): the /audit endpoint filters by action, admin, since."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from api.admin import ops
from core.db import SessionFactory, engine
from core.models import AdminAuditLog, AdminUser, Base
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _admin(session, role="admin") -> AdminUser:
    a = AdminUser(email="a@x.io", password_hash=hash_password("x"), role=role, is_active=True)
    session.add(a)
    await session.commit()
    return a


async def _seed(session):
    now = datetime.now(UTC)
    session.add_all([
        AdminAuditLog(admin_id=1, action="business_config.update", created_at=now),
        AdminAuditLog(admin_id=2, action="ai.account.create", created_at=now - timedelta(days=2)),
        AdminAuditLog(admin_id=1, action="ai.model.upsert", created_at=now - timedelta(days=5)),
    ])
    await session.commit()


async def test_no_filter_returns_all():
    async with SessionFactory() as s:
        admin = await _admin(s)
        await _seed(s)
        out = await ops.list_audit(admin=admin, session=s)
        assert len(out) == 3


async def test_filter_by_action_substring():
    async with SessionFactory() as s:
        admin = await _admin(s)
        await _seed(s)
        out = await ops.list_audit(action="ai.", admin=admin, session=s)
        assert {o["action"] for o in out} == {"ai.account.create", "ai.model.upsert"}


async def test_filter_by_admin_and_since():
    async with SessionFactory() as s:
        admin = await _admin(s)
        await _seed(s)
        out = await ops.list_audit(admin_id=1, admin=admin, session=s)
        assert all(o["admin_id"] == 1 for o in out) and len(out) == 2

        since = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        recent = await ops.list_audit(since=since, admin=admin, session=s)
        assert {o["action"] for o in recent} == {"business_config.update"}


async def test_bad_since_400():
    async with SessionFactory() as s:
        admin = await _admin(s)
        await _seed(s)
        with pytest.raises(Exception):  # noqa: B017,PT011 — HTTPException(400)
            await ops.list_audit(since="not-a-date", admin=admin, session=s)


# ---- full server-side CSV export -------------------------------------------
import types  # noqa: E402


def _req():
    return types.SimpleNamespace(client=types.SimpleNamespace(host="1.2.3.4"))


async def _read_csv(resp) -> str:
    chunks = []
    async for c in resp.body_iterator:
        chunks.append(c if isinstance(c, str) else c.decode())
    return "".join(chunks)


async def test_export_csv_covers_all_filtered_rows():
    async with SessionFactory() as s:
        admin = await _admin(s)
        await _seed(s)
        resp = await ops.export_audit_csv(_req(), action="ai.", admin=admin, session=s)
        body = await _read_csv(resp)
    lines = [ln for ln in body.splitlines() if ln.strip()]
    # header + the two ai.* rows (NOT page-limited)
    assert lines[0].startswith("id,created_at,action,category")
    assert len(lines) == 3
    assert any("ai.account.create" in ln for ln in lines)
    assert any("ai.model.upsert" in ln for ln in lines)
    assert "business_config.update" not in body
    assert resp.headers["content-disposition"].endswith('filename="audit-export.csv"')


async def test_export_csv_is_audited():
    async with SessionFactory() as s:
        admin = await _admin(s)
        await _seed(s)
        await ops.export_audit_csv(_req(), admin=admin, session=s)
        # the export itself is recorded
        from sqlalchemy import select
        rows = (await s.scalars(
            select(AdminAuditLog).where(AdminAuditLog.action == "export.audit")
        )).all()
        assert len(rows) == 1
        assert rows[0].target_id == "audit.csv"


async def test_export_csv_formula_injection_safe():
    async with SessionFactory() as s:
        admin = await _admin(s)
        # a target_id that Excel would treat as a formula
        s.add(AdminAuditLog(admin_id=1, action="user.note", target_type="user",
                            target_id="=cmd|calc"))
        await s.commit()
        resp = await ops.export_audit_csv(_req(), admin=admin, session=s)
        body = await _read_csv(resp)
    # neutralized with a leading apostrophe (OWASP), so it isn't a live formula
    assert "'=cmd|calc" in body
