"""Admin: manage panel admins — list / create / disable / role changes (ТЗ §8).

Superadmin-only and fully audited. We never return password hashes or 2FA
secrets (only a boolean `has_2fa`). The "last active superadmin" is protected:
it can't be demoted or disabled, so the panel can never lock everyone out.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core.db import get_session
from core.models import AdminAuditLog, AdminUser
from core.services.admin_auth import ROLE_RANK, hash_password

router = APIRouter(prefix="/admins", tags=["admin-admins"])

# Roles assignable from the panel — the full RBAC set (see admin_auth.ROLE_RANK).
ALLOWED_ROLES = set(ROLE_RANK)


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _iso(a: AdminUser, field: str) -> str | None:
    """ISO-format a timestamp column, but NEVER trigger a lazy load: created_at /
    updated_at are pure server-defaults (func.now(), no Python-side default), so on a
    freshly-added object that wasn't refreshed they are *unloaded* — touching them in
    async code raises MissingGreenlet. Listed rows are SELECTed fresh (loaded), so the
    real value is returned there; only un-refreshed instances fall back to None."""
    if field in inspect(a).unloaded:
        return None
    val = getattr(a, field)
    return val.isoformat() if val else None


def _serialize(a: AdminUser) -> dict:
    # Only non-sensitive fields. We expose timestamps + token_version (all already
    # on the model — no migration) so the panel can show last-login, account age and
    # the session generation. Password hash and TOTP secret are NEVER returned.
    return {
        "id": a.id,
        "email": a.email,
        "role": a.role,
        "is_active": a.is_active,
        "has_2fa": bool(a.totp_secret),
        "last_login": _iso(a, "last_login"),
        "created_at": _iso(a, "created_at"),
        "updated_at": _iso(a, "updated_at"),
        # Bumped on logout / disable / password+2FA change — every previously-issued
        # token carrying an older value is rejected. Acts as a "session generation".
        "token_version": a.token_version,
    }


async def _active_superadmin_count(session: AsyncSession) -> int:
    return await session.scalar(
        select(func.count())
        .select_from(AdminUser)
        .where(AdminUser.role == "superadmin", AdminUser.is_active.is_(True))
    )


async def _is_last_active_superadmin(session: AsyncSession, admin: AdminUser) -> bool:
    """True if `admin` is the only remaining active superadmin — demoting or
    disabling it would leave the panel with zero superadmins."""
    if admin.role != "superadmin" or not admin.is_active:
        return False
    return (await _active_superadmin_count(session)) <= 1


@router.get("")
async def list_admins(
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (await session.scalars(select(AdminUser).order_by(AdminUser.id))).all()
    return [_serialize(a) for a in rows]


class CreateAdmin(BaseModel):
    email: str = Field(..., max_length=320)          # FIX: AUDIT13-L18
    password: str = Field(..., max_length=256)
    role: str = Field(..., max_length=20)


@router.post("")
async def create_admin(
    req: CreateAdmin,
    request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    email = req.email.strip().lower()
    if not email or not req.password:
        raise HTTPException(status_code=400, detail="email and password required")
    # FIX: AUDIT-93 - password min length
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="password must be at least 8 characters")
    if req.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="invalid role")
    existing = await session.scalar(
        select(AdminUser).where(func.lower(AdminUser.email) == email)
    )
    if existing is not None:
        raise HTTPException(status_code=400, detail="email already exists")
    new = AdminUser(
        email=email,
        password_hash=hash_password(req.password),
        role=req.role,
        is_active=True,
    )
    session.add(new)
    await session.flush()
    await audit(
        session, admin_id=admin.id, action="admin.create",
        target_type="admin", target_id=str(new.id),
        after={"email": email, "role": req.role}, ip=_ip(request),
    )
    return _serialize(new)


class RoleChange(BaseModel):
    role: str


@router.put("/{admin_id}/role")
async def set_admin_role(
    admin_id: int,
    req: RoleChange,
    request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if req.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="invalid role")
    target = await session.get(AdminUser, admin_id)
    if target is None:
        raise HTTPException(status_code=404, detail="admin not found")
    # FIX: SUPERADMIN-1 - self-demotion guard. A superadmin demoting themselves
    # to a lower role is the single most common way panels get locked out: the
    # action succeeds, the session JWT still says "superadmin" until refresh,
    # the admin reloads, and now NOBODY can reach /admins to fix it. Require
    # a second superadmin to perform the demotion (the last-superadmin check
    # below already covers the 1-superadmin edge case).
    if target.id == admin.id and req.role != "superadmin":
        raise HTTPException(status_code=400, detail="cannot demote yourself; ask another superadmin")
    # FIX: R16 - lock the target row so the last-superadmin check + the role write
    # are atomic. Without this, two concurrent demotions of the last two superadmins
    # could both pass the count check and leave the panel with zero superadmins.
    await session.refresh(target, with_for_update=True)
    before_role = target.role
    if req.role != "superadmin" and await _is_last_active_superadmin(session, target):
        raise HTTPException(status_code=400, detail="cannot demote the last superadmin")
    target.role = req.role
    await audit(
        session, admin_id=admin.id, action="admin.role",
        target_type="admin", target_id=str(target.id),
        before={"role": before_role}, after={"role": req.role}, ip=_ip(request),
    )
    return _serialize(target)


@router.post("/{admin_id}/disable")
async def disable_admin(
    admin_id: int,
    request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    target = await session.get(AdminUser, admin_id)
    if target is None:
        raise HTTPException(status_code=404, detail="admin not found")
    # FIX: SUPERADMIN-2 - self-disable guard. Disabling your own account bumps
    # your token_version mid-session, so the very next API call 401s and you
    # are logged out — with no way back in if you were the only superadmin.
    # Use logout-all on yourself, or ask another superadmin to disable you.
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="cannot disable yourself; use logout instead")
    # FIX: R16 - same lock+re-check discipline as set_admin_role (R16).
    await session.refresh(target, with_for_update=True)
    if await _is_last_active_superadmin(session, target):
        raise HTTPException(status_code=400, detail="cannot disable the last superadmin")
    target.is_active = False
    # Bump token_version so any already-issued access/refresh tokens are rejected.
    target.token_version += 1
    await audit(
        session, admin_id=admin.id, action="admin.disable",
        target_type="admin", target_id=str(target.id),
        after={"is_active": False}, ip=_ip(request),
    )
    return _serialize(target)


@router.post("/{admin_id}/enable")
async def enable_admin(
    admin_id: int,
    request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    target = await session.get(AdminUser, admin_id)
    if target is None:
        raise HTTPException(status_code=404, detail="admin not found")
    # FIX: M8 - lock row so a concurrent disable_admin can't be overwritten.
    await session.refresh(target, with_for_update=True)
    target.is_active = True
    await audit(
        session, admin_id=admin.id, action="admin.enable",
        target_type="admin", target_id=str(target.id),
        after={"is_active": True}, ip=_ip(request),
    )
    return _serialize(target)


@router.post("/{admin_id}/reset-2fa")
async def reset_admin_2fa(
    admin_id: int,
    request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Clear an admin's 2FA secret so they can re-enroll (e.g. lost device)."""
    target = await session.get(AdminUser, admin_id)
    if target is None:
        raise HTTPException(status_code=404, detail="admin not found")
    # FIX: M7 - lock row before clearing totp_secret (was: no with_for_update, unlike
    # R16 applied to set_admin_role/disable_admin).
    await session.refresh(target, with_for_update=True)
    target.totp_secret = None
    # FIX: F17 - bump token_version so every previously-issued access/refresh token
    # (issued when 2FA was active) is immediately rejected. Without this, an admin
    # whose 2FA was reset keeps using their existing (possibly compromised) sessions
    # with no 2FA challenge. Mirror disable_admin / logout_all_admin.
    target.token_version += 1
    await audit(
        session, admin_id=admin.id, action="admin.reset_2fa",
        target_type="admin", target_id=str(target.id), ip=_ip(request),
    )
    return _serialize(target)


def _device_label(ua: str) -> str:
    """Compact, human label for a user-agent string (browser · OS), best-effort."""
    if not ua:
        return "неизвестно"
    low = ua.lower()
    browser = next((b for k, b in (("edg", "Edge"), ("chrome", "Chrome"), ("firefox", "Firefox"),
                                   ("safari", "Safari"), ("curl", "curl"), ("python", "script"))
                    if k in low), "браузер")
    osname = next((o for k, o in (("windows", "Windows"), ("android", "Android"),
                                  ("iphone", "iPhone"), ("ipad", "iPad"),
                                  ("mac os", "macOS"), ("linux", "Linux"))
                   if k in low), "")
    return f"{browser}{f' · {osname}' if osname else ''}"


@router.get("/{admin_id}/sessions")
async def admin_sessions(
    admin_id: int,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Active sessions for an admin, derived from successful logins in the audit log
    (JWTs are stateless, so a 'session' = a distinct device+IP that logged in). Each
    entry: device, ip, last login, count. Honest approximation — not socket-level."""
    rows = (await session.scalars(
        select(AdminAuditLog)
        .where(AdminAuditLog.admin_id == admin_id, AdminAuditLog.action == "auth.login")
        .order_by(AdminAuditLog.created_at.desc())
        .limit(200)
    )).all()
    buckets: dict[tuple[str, str], dict] = {}
    for r in rows:
        device = _device_label((r.after or {}).get("device", "")) if r.after else "неизвестно"
        ip = r.ip or "—"
        key = (device, ip)
        b = buckets.get(key)
        if b is None:
            buckets[key] = {
                "device": device, "ip": ip,
                "last_at": r.created_at.isoformat() if r.created_at else None,
                "count": 1,
            }
        else:
            b["count"] += 1
    sessions = sorted(buckets.values(), key=lambda x: x["last_at"] or "", reverse=True)
    return {"sessions": sessions}


@router.post("/{admin_id}/logout-all")
async def logout_all_admin(
    admin_id: int,
    request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """End ALL of an admin's sessions by bumping token_version — every issued access
    and refresh token is invalidated at once (the account stays active and can log in
    again). The real revoke-all for stateless JWTs."""
    target = await session.get(AdminUser, admin_id)
    if target is None:
        raise HTTPException(status_code=404, detail="admin not found")
    target.token_version += 1
    await audit(
        session, admin_id=admin.id, action="admin.logout_all",
        target_type="admin", target_id=str(target.id), ip=_ip(request),
    )
    return _serialize(target)
