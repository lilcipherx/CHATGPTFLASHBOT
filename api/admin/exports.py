"""Admin: CSV exports of users and payments (ТЗ §8).

The admin downloads the users / payments tables as CSV. Each export is audited.

NOTE: these endpoints currently build the whole CSV in memory from a single
bounded-but-full query. That is fine for the present scale, but a very large
export should later stream from a server-side cursor (e.g. an async
`yield_per` / keyset-paginated generator) so memory stays O(1) instead of
O(rows). The pure `_rows_to_csv` helper is kept separate precisely so the row
source can be swapped for a streaming generator without touching CSV shaping.
"""
from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import like_contains, require_role
from core.db import get_session
from core.models import AdminUser, Transaction, User

router = APIRouter(prefix="/exports", tags=["admin-exports"])
log = structlog.get_logger()  # FIX: AUDIT12-M2 - export cap warning

# FIX: AUDIT12-M2 - OOM protection for export_payments. Mirrors the AUDIT-165 cap
# on export_users but ALSO surfaces the truncation to the admin via a response
# header + a structlog warning so a silent partial-export can't be mistaken for
# the full data set (200k paid txs ≈ multi-year history for a mid-size bot).
PAYMENTS_ROWS_CAP = 200_000

USERS_HEADER = [
    "user_id", "username", "sub_tier", "is_premium", "is_banned",
    "credits", "country", "created_at",
]
PAYMENTS_HEADER = [
    "tx_id", "gateway_tx_id", "user_id", "product", "amount", "currency",
    "gateway", "status", "created_at",
]


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


# CSV formula-injection (CWE-1236): a cell beginning with one of these is treated
# as a formula by Excel/Sheets/LibreOffice when the admin opens the file. Neutralize
# by prefixing an apostrophe (OWASP mitigation). Applied to STRING cells only, so
# numeric values (e.g. a negative amount "-5") are never mangled.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(v: object) -> object:
    if v is None:
        return ""
    if isinstance(v, str) and v and v[0] in _CSV_FORMULA_PREFIXES:
        return "'" + v
    return v


def _rows_to_csv(header: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    """Render a header row + data rows to a CSV string (pure, unit-testable).

    Data cells are passed through ``_csv_safe`` to defuse spreadsheet formula
    injection from any user-influenced field."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_csv_safe(v) for v in row])
    return buf.getvalue()


def _csv_response(
    filename: str, body: str, *, extra_headers: dict[str, str] | None = None,
) -> StreamingResponse:
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if extra_headers:
        headers.update(extra_headers)
    return StreamingResponse(
        iter([body]),
        media_type="text/csv",
        headers=headers,
    )


@router.get("/users.csv")
async def export_users(
    request: Request,
    q: str = "",
    premium: bool | None = None,
    banned: bool | None = None,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Full users export as CSV. Optional q/premium/banned filters mirror the
    users list endpoint."""
    # FIX: AUDIT-165 - row cap to prevent OOM
    stmt = select(User).order_by(User.created_at.desc()).limit(200_000)
    if q:
        like = like_contains(q)
        conds = [User.username.ilike(like, escape="\\"), User.phone.ilike(like, escape="\\")]
        if q.isdigit():
            conds.append(User.user_id == int(q))
        stmt = stmt.where(or_(*conds))
    if premium is not None:
        now = datetime.now(UTC)
        if premium:
            stmt = stmt.where(
                User.sub_tier.isnot(None),
                User.sub_expires.isnot(None),
                User.sub_expires > now,
            )
        else:
            stmt = stmt.where(
                or_(User.sub_tier.is_(None), User.sub_expires.is_(None),
                    User.sub_expires <= now)
            )
    if banned is not None:
        stmt = stmt.where(User.is_banned.is_(banned))

    users = (await session.scalars(stmt)).all()
    rows = [
        [u.user_id, u.username, u.sub_tier, u.is_premium, u.is_banned,
         u.credits, u.country, u.created_at.isoformat() if u.created_at else ""]
        for u in users
    ]
    body = _rows_to_csv(USERS_HEADER, rows)
    await audit(session, admin_id=admin.id, action="export.users",
                target_type="export", target_id="users.csv",
                after={"rows": len(rows)}, ip=_ip(request))
    return _csv_response("users.csv", body)


@router.get("/payments.csv")
async def export_payments(
    request: Request,
    status: str | None = None,
    gateway: str | None = None,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Paid-transactions export as CSV. Optional status/gateway filters; defaults
    to status='paid'."""
    stmt = select(Transaction).order_by(Transaction.created_at.desc())
    stmt = stmt.where(Transaction.status == (status or "paid"))
    if gateway:
        stmt = stmt.where(Transaction.gateway == gateway)

    # FIX: AUDIT12-M2 - row cap to prevent OOM (mirrors export_users AUDIT-165).
    rows = (await session.scalars(stmt.limit(PAYMENTS_ROWS_CAP))).all()
    capped = len(rows) == PAYMENTS_ROWS_CAP
    if capped:
        log.warning("export_payments.row_cap_hit", cap=PAYMENTS_ROWS_CAP)
    txs = rows
    csv_rows = [
        [str(t.tx_id), t.gateway_tx_id, t.user_id, t.product, t.amount,
         t.currency, t.gateway, t.status,
         t.created_at.isoformat() if t.created_at else ""]
        for t in txs
    ]
    body = _rows_to_csv(PAYMENTS_HEADER, csv_rows)
    await audit(session, admin_id=admin.id, action="export.payments",
                target_type="export", target_id="payments.csv",
                after={"rows": len(csv_rows), "truncated": capped}, ip=_ip(request))
    # FIX: AUDIT12-M2 - surface truncation to the admin so a partial export can't
    # be mistaken for the full data set. Two signals: a custom X-Export-Truncated
    # response header (machine-readable) + a prepended notice line in the body.
    extra_headers: dict[str, str] = {}
    if capped:
        extra_headers["X-Export-Truncated"] = "true"
        extra_headers["X-Export-Row-Cap"] = str(PAYMENTS_ROWS_CAP)
        body = (
            f"# NOTICE: export capped at {PAYMENTS_ROWS_CAP} rows (newest-first). "
            f"Use the status/gateway filters to narrow the window.\r\n"
            + body
        )
    return _csv_response("payments.csv", body, extra_headers=extra_headers or None)
