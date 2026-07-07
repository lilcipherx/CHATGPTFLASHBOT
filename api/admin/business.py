"""Admin: live business configuration — prices + limits (ТЗ §1).

Typed, audited read/write over core.services.pricing. (The raw `pricing` table is
also reachable via the generic /pricing endpoint, but this gives a stable shape +
the defaults so the UI can render a structured form.) Read = admin; write =
superadmin, mirroring the existing /pricing write gate (money is superadmin-only).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core.db import get_session
from core.models import AdminUser, CustomButtonStat
from core.services import pricing

router = APIRouter(prefix="/business-config", tags=["admin-business"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.get("")
async def get_business_config(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Current merged config + the static defaults (so the UI can show what a field
    falls back to)."""
    return {"config": await pricing.get_config(session), "defaults": pricing.defaults()}


@router.get("/button-stats")
async def get_button_stats(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Per-button click counts (button_id -> clicks) from the /r/{id} redirect tracker,
    so the buttons page can show real engagement instead of a placeholder."""
    rows = (await session.scalars(select(CustomButtonStat))).all()
    return {"clicks": {r.button_id: r.clicks for r in rows}}


class ConfigPatch(BaseModel):
    patch: dict


@router.put("")
async def set_business_config(
    req: ConfigPatch,
    request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Apply a partial override (deep-merged; unknown top-level keys ignored) and
    return the new merged config. Applies live (Redis cache invalidated)."""
    cfg = await pricing.set_config(session, req.patch)
    await audit(
        session, admin_id=admin.id, action="business_config.update",
        target_type="config", target_id="business_config", after=req.patch, ip=_ip(request),
    )
    return {"ok": True, "config": cfg}
