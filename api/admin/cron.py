"""Admin: Scheduler control (ТЗ §8) — turn each beat cron job on/off and set how
often it runs, at runtime (no redeploy). Backed by core.services.cron_control; the
beat scheduler reads those rows on every tick. See workers.main.

* ``GET  /cron``          — list all jobs + their enabled/interval/last-run state.
* ``POST /cron/{name}``   — update a job's enabled flag and/or interval (superadmin).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core.db import get_session
from core.models import AdminUser
from core.services import cron_control

router = APIRouter(prefix="/cron", tags=["admin-cron"])


class CronUpdate(BaseModel):
    enabled: bool | None = None
    # Bounded to the same [MIN, MAX] the service clamps to, so the API rejects garbage.
    interval_seconds: int | None = Field(
        default=None, ge=cron_control.MIN_INTERVAL, le=cron_control.MAX_INTERVAL
    )


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.get("")
async def list_cron(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """All scheduler jobs with their current on/off state, interval and last run."""
    return {"jobs": await cron_control.list_jobs(session)}


@router.post("/{name}")
async def update_cron(
    name: str,
    body: CronUpdate,
    request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Enable/disable a job and/or change how often it runs. Only superadmin; audited."""
    if body.enabled is None and body.interval_seconds is None:
        raise HTTPException(status_code=400, detail="nothing to update")
    try:
        job = await cron_control.set_config(
            session, name, enabled=body.enabled, interval_seconds=body.interval_seconds
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown cron job") from exc
    await audit(
        session, admin_id=admin.id, action="cron.update",
        target_type="cron", target_id=name,
        after={"enabled": job["enabled"], "interval_seconds": job["interval_seconds"]},
        ip=_ip(request), commit=True,
    )
    return {"ok": True, "job": job}
