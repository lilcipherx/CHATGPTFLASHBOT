"""Admin API dependencies: IP allow-list, JWT bearer auth, RBAC (§11A.1)."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.db import get_session
from core.models import AdminUser
from core.services.admin_auth import decode_token, role_allows


def like_contains(term: str) -> str:
    r"""A LIKE pattern matching ``term`` as a LITERAL substring. Escapes the LIKE
    metacharacters (``%`` ``_`` and the ``\`` escape char itself) so a user who types
    them searches for those characters instead of widening the match to everything.
    Pair with ``.ilike(pattern, escape="\\")`` at the call site."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _allowlist() -> set[str]:
    return {ip.strip() for ip in settings.admin_ip_allowlist.split(",") if ip.strip()}


async def ip_allowlisted(request: Request) -> None:
    allow = _allowlist()
    if not allow:  # empty list = open (dev)
        return
    client = request.client.host if request.client else ""
    if client not in allow:
        raise HTTPException(status_code=403, detail="ip_not_allowed")


async def _admin_from_token(
    authorization: str,
    admin_access: str,
    session: AsyncSession,
    *,
    allowed_scopes: set[str],
) -> AdminUser:
    # Prefer the httpOnly `admin_access` cookie — it is NOT readable from JS, so an
    # XSS payload can't exfiltrate it. Fall back to the Authorization header for
    # non-browser API clients and cross-origin dev (vite on a different port).
    token = admin_access or (
        authorization[7:] if authorization.startswith("Bearer ") else ""
    )
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="not an access token")
    # Tokens predating the scope claim are treated as "full".
    if payload.get("scope", "full") not in allowed_scopes:
        raise HTTPException(status_code=403, detail="mfa_setup_required")
    admin = await session.get(AdminUser, int(payload["sub"]))
    if admin is None or not admin.is_active:
        raise HTTPException(status_code=401, detail="admin inactive")
    if payload.get("ver") != admin.token_version:
        raise HTTPException(status_code=401, detail="token revoked")
    return admin


async def current_admin(
    _: None = Depends(ip_allowlisted),
    authorization: str = Header(default=""),
    admin_access: str = Cookie(default=""),
    session: AsyncSession = Depends(get_session),
) -> AdminUser:
    """Full admin session — rejects the restricted mfa_setup scope, so an admin who
    still owes 2FA enrollment cannot reach any real admin endpoint (§8)."""
    return await _admin_from_token(
        authorization, admin_access, session, allowed_scopes={"full"}
    )


async def current_admin_enrolling(
    _: None = Depends(ip_allowlisted),
    authorization: str = Header(default=""),
    admin_access: str = Cookie(default=""),
    session: AsyncSession = Depends(get_session),
) -> AdminUser:
    """Looser session for the 2FA self-service endpoints only: accepts both a full
    session and the restricted mfa_setup scope, so a freshly-logged-in admin who is
    being forced to enroll can actually call /2fa/setup and /2fa/enable."""
    return await _admin_from_token(
        authorization, admin_access, session, allowed_scopes={"full", "mfa_setup"}
    )


def require_role(*roles: str) -> Callable:
    async def _checker(admin: AdminUser = Depends(current_admin)) -> AdminUser:
        if not role_allows(admin.role, *roles):
            raise HTTPException(status_code=403, detail="insufficient role")
        return admin

    return _checker
