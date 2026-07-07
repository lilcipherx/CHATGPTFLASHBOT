"""Admin: traffic-source attribution (ТЗ §7).

Signups grouped by the first-touch deep-link token captured at /start
(users.source). NULL sources are surfaced as the "(direct)" bucket.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.deps import require_role
from core.db import get_session
from core.models import AdminUser, User

router = APIRouter(prefix="/traffic", tags=["admin-traffic"])

_DIRECT = "(direct)"


@router.get("/sources")
async def traffic_sources(
    days: int | None = Query(default=None, ge=1, le=3650),
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Signup counts grouped by users.source (NULL -> "(direct)").

    Ordered busiest-first. `days` limits to users whose created_at falls within the
    last N days.
    """
    stmt = select(User.source, func.count()).group_by(User.source)
    if days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        stmt = stmt.where(User.created_at >= cutoff)

    rows = (await session.execute(stmt)).all()
    out = [{"source": src if src is not None else _DIRECT, "users": count} for src, count in rows]
    out.sort(key=lambda r: r["users"], reverse=True)
    return out
