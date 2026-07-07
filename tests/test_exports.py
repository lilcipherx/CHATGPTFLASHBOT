"""Admin CSV exports (api/admin/exports) — ТЗ §8.

Unit-tests the pure `_rows_to_csv` helper, plus light endpoint smoke tests that
call the endpoint coroutines directly (mirroring tests/test_business_admin) and
read the StreamingResponse body.
"""
from __future__ import annotations

import csv
import io
import types
import uuid
from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy import func, select

from api.admin import exports
from core.db import SessionFactory, engine
from core.models import AdminAuditLog, AdminUser, Base, Transaction, User
from core.services.admin_auth import hash_password


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req():
    return types.SimpleNamespace(client=None)


async def _admin(session, role="admin") -> AdminUser:
    a = AdminUser(email="e@x.io", password_hash=hash_password("x"), role=role, is_active=True)
    session.add(a)
    await session.commit()
    return a


async def _read_body(resp) -> str:
    chunks = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return "".join(chunks)


# ---------- pure helper ----------
async def test_rows_to_csv_header_and_rows():
    out = exports._rows_to_csv(["a", "b"], [[1, "x"], [2, None]])
    parsed = list(csv.reader(io.StringIO(out)))
    assert parsed[0] == ["a", "b"]
    assert parsed[1] == ["1", "x"]
    assert parsed[2] == ["2", ""]  # None -> empty cell


async def test_rows_to_csv_defuses_formula_injection():
    # Formula-leading STRING cells are prefixed with ' (CWE-1236); numbers untouched.
    out = exports._rows_to_csv(
        ["x"],
        [["=cmd|'/c calc'!A1"], ["+1+1"], ["-2+3"], ["@SUM(A1)"], ["safe"], [-5], [3]],
    )
    parsed = list(csv.reader(io.StringIO(out)))
    assert parsed[1] == ["'=cmd|'/c calc'!A1"]
    assert parsed[2] == ["'+1+1"]
    assert parsed[3] == ["'-2+3"]
    assert parsed[4] == ["'@SUM(A1)"]
    assert parsed[5] == ["safe"]
    assert parsed[6] == ["-5"]   # negative number NOT mangled
    assert parsed[7] == ["3"]


# ---------- endpoints ----------
async def test_export_users_smoke():
    async with SessionFactory() as s:
        a = await _admin(s)
        s.add_all([
            User(user_id=111, username="alice", credits=5, country="US"),
            User(user_id=222, username="bob", credits=0, is_banned=True),
        ])
        await s.commit()

        resp = await exports.export_users(_req(), admin=a, session=s)
        assert resp.media_type == "text/csv"
        assert 'filename="users.csv"' in resp.headers["content-disposition"]
        body = await _read_body(resp)

    parsed = list(csv.reader(io.StringIO(body)))
    assert parsed[0] == exports.USERS_HEADER
    ids = {row[0] for row in parsed[1:]}
    assert {"111", "222"} <= ids
    # an audit row was written
    async with SessionFactory() as s:
        n = await s.scalar(
            select(func.count()).select_from(AdminAuditLog)
            .where(AdminAuditLog.action == "export.users")
        )
        assert n == 1


async def test_export_payments_smoke():
    async with SessionFactory() as s:
        a = await _admin(s)
        s.add(User(user_id=333, username="carol"))
        s.add(Transaction(
            tx_id=uuid.uuid4(), user_id=333, product="premium", amount=499,
            currency="rub", gateway="yookassa", status="paid",
            gateway_tx_id="gw-abc", created_at=datetime.now(UTC),
        ))
        # a non-paid tx should be excluded by the default status='paid' filter
        s.add(Transaction(
            tx_id=uuid.uuid4(), user_id=333, product="credits", amount=100,
            currency="rub", gateway="yookassa", status="pending",
            created_at=datetime.now(UTC),
        ))
        await s.commit()

        resp = await exports.export_payments(_req(), admin=a, session=s)
        body = await _read_body(resp)

    parsed = list(csv.reader(io.StringIO(body)))
    assert parsed[0] == exports.PAYMENTS_HEADER
    data = parsed[1:]
    assert len(data) == 1                      # only the paid tx
    assert data[0][1] == "gw-abc"              # gateway_tx_id column
    assert data[0][2] == "333"                 # user_id
    assert data[0][7] == "paid"                # status
