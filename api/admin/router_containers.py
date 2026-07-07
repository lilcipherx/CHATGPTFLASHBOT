"""Admin: управление контейнерами роутеров (ТЗ §2, только superadmin).

Старт/стоп/рестарт и инспекция self-hosted LiteLLM-роутера прямо из панели. Вся
фича выключена по умолчанию (``settings.router_mgmt_enabled``) — она обращается к
``docker compose`` (доступ к хосту), поэтому это осознанный opt-in. Управлять можно
ТОЛЬКО сервисами из фиксированного allowlist; каждое действие пишется в аудит.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core.db import get_session
from core.models import AdminUser
from core.services import router_containers as rc

router = APIRouter(prefix="/routers", tags=["admin-routers"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _result(r: rc.CmdResult) -> dict:
    return {"ok": r.ok, "code": r.code, "stdout": r.stdout, "stderr": r.stderr}


def _translate(exc: Exception) -> HTTPException:
    """Map service-layer guards to HTTP: disabled → 403, unknown service → 404."""
    if isinstance(exc, rc.RouterMgmtDisabled):
        return HTTPException(status_code=403, detail="router management disabled")
    if isinstance(exc, rc.UnknownRouter):
        return HTTPException(status_code=404, detail="unknown router")
    return HTTPException(status_code=400, detail=str(exc))


@router.get("")
async def list_routers(
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Manageable router services + whether the feature is enabled."""
    return {"enabled": rc.is_enabled(), "services": list(rc.ROUTER_SERVICES)}


@router.get("/{service}/status")
async def router_status(
    service: str,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        return _result(await rc.status(service))
    except (rc.RouterMgmtDisabled, rc.UnknownRouter) as exc:
        raise _translate(exc) from exc


@router.get("/{service}/logs")
async def router_logs(
    service: str, tail: int = 200,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        return _result(await rc.logs(service, tail))
    except (rc.RouterMgmtDisabled, rc.UnknownRouter) as exc:
        raise _translate(exc) from exc


@router.post("/{service}/{verb}")
async def router_action(
    service: str, verb: str, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """start | stop | restart a router container (superadmin, audited)."""
    if verb not in rc.ACTIONS:
        raise HTTPException(status_code=404, detail="unknown action")
    try:
        result = await rc.action(service, verb)
    except (rc.RouterMgmtDisabled, rc.UnknownRouter) as exc:
        raise _translate(exc) from exc
    await audit(
        session, admin_id=admin.id, action=f"router.{verb}",
        target_type="router_container", target_id=service,
        after={"ok": result.ok, "code": result.code}, ip=_ip(request),
    )
    return _result(result)
