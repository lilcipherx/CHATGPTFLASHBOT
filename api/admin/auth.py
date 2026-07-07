"""Admin auth: email+password (+ TOTP 2FA) login → JWT (access + refresh)."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import (
    current_admin,
    current_admin_enrolling,
    ip_allowlisted,
    require_role,
)
from core.config import settings
from core.db import get_session
from core.models import AdminAuditLog, AdminUser
from core.services import ratelimit
from core.services.admin_auth import (
    ACCESS_TTL,
    REFRESH_TTL,
    ROLE_RANK,
    create_token,
    decode_token,
    hash_password,
    mfa_required,
    new_totp_secret,
    totp_uri,
    verify_password,
    verify_password_dummy,
    verify_totp,
)

router = APIRouter(prefix="/auth", tags=["admin-auth"])

# httpOnly access-token cookie — the primary credential for the browser SPA, so
# the token never lives in JS-readable storage (XSS can't steal it). Scoped to the
# admin API path; SameSite=strict blocks cross-site sending (CSRF defence);
# Secure outside dev so it is only sent over HTTPS.
ACCESS_COOKIE = "admin_access"
ACCESS_COOKIE_PATH = "/api/admin"
# Refresh token lives in its own httpOnly cookie scoped to the auth endpoints only
# (so it is never sent to ordinary admin APIs). It outlives the 30-min access token
# (REFRESH_TTL = 7d), letting the SPA silently mint a fresh access token on a 401 —
# sessions survive reloads + idle without re-login, while access tokens stay short.
REFRESH_COOKIE = "admin_refresh"
REFRESH_COOKIE_PATH = "/api/admin/auth"


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


async def _audit_login(
    session: AsyncSession, *, admin_id: int, success: bool, reason: str,
    email: str, ip: str, user_agent: str = "",
) -> None:
    """Record an admin authentication attempt in the audit trail (§8 security).

    Both successes and failures are logged so the Security Center can surface login
    history, failed attempts and brute-force signals. ``admin_id`` is 0 for an
    unknown email (no FK on admin_audit_log.admin_id, so this is safe); the attempted
    email + reason + device (user-agent) go into ``after`` for forensics / the active-
    sessions view. Audited via a stored substring "login", so the security-events
    filter picks it up."""
    await audit(
        session, admin_id=admin_id,
        action="auth.login" if success else "auth.login_failed",
        target_type="admin", target_id=str(admin_id) if admin_id else None,
        after={"email": email, "reason": reason, "success": success, "device": user_agent[:200]},
        ip=ip,
    )


def _set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        ACCESS_COOKIE,
        token,
        max_age=int(ACCESS_TTL.total_seconds()),
        httponly=True,
        samesite="strict",
        secure=settings.env not in ("dev", "test"),
        path=ACCESS_COOKIE_PATH,
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=int(REFRESH_TTL.total_seconds()),
        httponly=True,
        samesite="strict",
        secure=settings.env not in ("dev", "test"),
        path=REFRESH_COOKIE_PATH,
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path=ACCESS_COOKIE_PATH)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


class LoginRequest(BaseModel):
    # FIX: AUDIT13-L18 - bound credential fields on the unauthenticated path so a huge
    # password can't inflate argon2 CPU per request (rate-limit already mitigates).
    email: str = Field(..., max_length=320)
    password: str = Field(..., max_length=256)
    otp: str | None = Field(None, max_length=16)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    role: str
    # True when the session is restricted to 2FA enrollment: the role mandates 2FA
    # (§8) but no secret is set yet. The SPA must route straight to setup.
    mfa_setup_required: bool = False


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    response: Response,
    request: Request,
    _: None = Depends(ip_allowlisted),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    email = req.email.strip().lower()
    ip = _ip(request)
    ua = request.headers.get("user-agent", "")  # device, for login history / sessions
    # Brute-force defence in depth (on top of slow argon2 + mandatory TOTP): cap login
    # attempts per source IP. 30 / 5 min is generous enough never to lock out a real
    # admin fumbling a password or OTP, but stops automated credential guessing cold.
    # Fixed-window Redis counter; on a Redis hiccup we fail OPEN so the panel stays
    # reachable — argon2 + 2FA remain the actual gate.
    try:
        within_limit = await ratelimit.allow(f"adminlogin:{ip}", 30, 300)
    except Exception:  # noqa: BLE001 — Redis down must not lock admins out
        within_limit = True
    if not within_limit:
        raise HTTPException(status_code=429, detail="too many attempts, try again later")
    # Case-insensitive match: mobile keyboards often auto-capitalize the email.
    admin = await session.scalar(
        select(AdminUser).where(func.lower(AdminUser.email) == email)
    )
    if admin is None or not admin.is_active:
        # No real hash to check — still spend argon2 time so an unknown/disabled
        # email is indistinguishable by latency from a real wrong password
        # (prevents account enumeration via response timing).
        verify_password_dummy(req.password)
        reason = "unknown_email" if admin is None else "inactive"
        await _audit_login(session, admin_id=admin.id if admin else 0,
                           success=False, reason=reason, email=email, ip=ip, user_agent=ua)
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not verify_password(req.password, admin.password_hash):
        await _audit_login(session, admin_id=admin.id,
                           success=False, reason="bad_password", email=email, ip=ip, user_agent=ua)
        raise HTTPException(status_code=401, detail="invalid credentials")

    if admin.totp_secret:
        if not req.otp:
            await _audit_login(session, admin_id=admin.id, success=False,
                               reason="otp_required", email=email, ip=ip, user_agent=ua)
            raise HTTPException(status_code=401, detail="otp_required")
        # FIX: AUDIT-1 - decrypt TOTP secret before verify
        from core.services.crypto import decrypt as _decrypt
        if not verify_totp(_decrypt(admin.totp_secret), req.otp):
            await _audit_login(session, admin_id=admin.id, success=False,
                               reason="otp_invalid", email=email, ip=ip, user_agent=ua)
            raise HTTPException(status_code=401, detail="otp_invalid")
    elif mfa_required(admin.role):
        # Password is correct, but this role must have 2FA and hasn't enrolled.
        # Hand back a restricted setup-scoped session: it can ONLY enroll 2FA
        # (every other admin endpoint rejects this scope). No refresh token —
        # the admin must complete enrollment and log in again. (§8)
        admin.last_login = datetime.now(UTC)
        await session.commit()
        setup = create_token(
            admin.id, admin.role, ver=admin.token_version, scope="mfa_setup"
        )
        _set_access_cookie(response, setup)
        await _audit_login(session, admin_id=admin.id, success=True,
                           reason="mfa_setup", email=email, ip=ip, user_agent=ua)
        return TokenResponse(
            access_token=setup,
            refresh_token="",
            role=admin.role,
            mfa_setup_required=True,
        )

    admin.last_login = datetime.now(UTC)
    await session.commit()
    access = create_token(admin.id, admin.role, ver=admin.token_version)
    refresh_tok = create_token(admin.id, admin.role, refresh=True, ver=admin.token_version)
    _set_access_cookie(response, access)
    _set_refresh_cookie(response, refresh_tok)
    await _audit_login(session, admin_id=admin.id, success=True,
                       reason="ok", email=email, ip=ip, user_agent=ua)
    return TokenResponse(
        # NOTE (AUDIT13-M12, deferred): tokens are also returned in the body (in addition
        # to the httpOnly+SameSite=strict cookies) for non-browser clients + the admin
        # SPA's initial hydration; existing tests and clients depend on this. Emptying
        # them (as /auth/refresh does via FINAL-6) is a defense-in-depth improvement but
        # needs coordinated client + test changes, so it is intentionally left as-is.
        access_token=access,
        refresh_token=refresh_tok,
        role=admin.role,
    )


class RefreshRequest(BaseModel):
    # Optional now: the refresh token is primarily read from the httpOnly
    # `admin_refresh` cookie. The body field is kept for non-browser/legacy callers.
    refresh_token: str | None = None


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    request: Request,
    req: RefreshRequest | None = None,
    _: None = Depends(ip_allowlisted),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    # Cookie is the primary source; fall back to the body for legacy/non-browser use.
    token = request.cookies.get(REFRESH_COOKIE) or (req.refresh_token if req else None)
    if not token:
        raise HTTPException(status_code=401, detail="no refresh token")
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="not a refresh token")
    admin = await session.get(AdminUser, int(payload["sub"]))
    if admin is None or not admin.is_active:
        raise HTTPException(status_code=401, detail="admin inactive")
    if payload.get("ver") != admin.token_version:
        raise HTTPException(status_code=401, detail="token revoked")
    access = create_token(admin.id, admin.role, ver=admin.token_version)
    refresh_tok = create_token(admin.id, admin.role, refresh=True, ver=admin.token_version)
    _set_access_cookie(response, access)
    _set_refresh_cookie(response, refresh_tok)  # rotate the refresh cookie too
    # FIX: AUDIT-98 - audit token refresh
    try:
        await audit(session, admin_id=admin.id, action="auth.token_refresh", target_type="admin", target_id=str(admin.id), ip=_ip(request), commit=False)
        await session.commit()
    except Exception as exc:
        import structlog
        structlog.get_logger().warning('api.admin.auth.refresh_failed', error=str(exc))
        # FIX: AUDIT12-L1 - was silent except: pass
    # FIX: FINAL-6 - tokens live ONLY in httpOnly cookies (set above). Returning
    # them in the JSON body made them XSS-readable, contradicting the AUDIT-99
    # hardening of /auth/login. Empty strings keep the response schema stable for
    # any legacy client that reads these fields.
    return TokenResponse(
        access_token="",
        refresh_token="",
        role=admin.role,
    )


# ---------- Two-factor auth (TOTP) self-service ----------
@router.get("/2fa/status")
async def twofa_status(admin: AdminUser = Depends(current_admin_enrolling)) -> dict:
    return {
        "enabled": bool(admin.totp_secret),
        "required": mfa_required(admin.role),
    }


@router.post("/2fa/setup")
async def twofa_setup(admin: AdminUser = Depends(current_admin_enrolling)) -> dict:
    """Generate a fresh secret + otpauth URI to add in an authenticator app. The
    secret is NOT saved until confirmed via /2fa/enable with a valid code."""
    secret = new_totp_secret()
    return {"secret": secret, "uri": totp_uri(secret, admin.email)}


class TwoFAEnable(BaseModel):
    secret: str
    code: str


@router.post("/2fa/enable")
async def twofa_enable(
    req: TwoFAEnable,
    response: Response,
    request: Request,  # FIX: B6 - required for _ip(request) in the audit call below
    admin: AdminUser = Depends(current_admin_enrolling),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Confirm setup: the code must match the proposed secret before we store it.
    Bumps token_version so the restricted setup-scoped session is invalidated — the
    admin must log in again, this time providing the OTP for a full session."""
    if not verify_totp(req.secret, req.code):
        raise HTTPException(status_code=400, detail="code_invalid")
    # FIX: AUDIT-1 - encrypt TOTP secret at rest
    from core.services.crypto import encrypt as _encrypt
    admin.totp_secret = _encrypt(req.secret)
    admin.token_version += 1
    # FIX: F18 - audit the 2FA-enable mutation (security-relevant; previously no trail).
    await audit(
        session, admin_id=admin.id, action="auth.2fa_enable",
        target_type="admin", target_id=str(admin.id),
        ip=_ip(request), commit=False,
    )
    await session.commit()
    response.delete_cookie(ACCESS_COOKIE, path=ACCESS_COOKIE_PATH)
    return {"ok": True, "enabled": True, "relogin_required": True}


class TwoFADisable(BaseModel):
    code: str


@router.post("/2fa/disable")
async def twofa_disable(
    req: TwoFADisable,
    request: Request,  # FIX: B7 - required for _ip(request) in the audit call below
    admin: AdminUser = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Turn 2FA off — requires a current valid code (proves possession)."""
    if not admin.totp_secret:
        return {"ok": True, "enabled": False}
    # FIX: AUDIT-1 - decrypt TOTP secret before verify on disable
    from core.services.crypto import decrypt as _decrypt
    if not verify_totp(_decrypt(admin.totp_secret), req.code):
        raise HTTPException(status_code=400, detail="code_invalid")
    admin.totp_secret = None
    # FIX: F19 - audit the 2FA-disable mutation (security regression; previously no trail).
    await audit(
        session, admin_id=admin.id, action="auth.2fa_disable",
        target_type="admin", target_id=str(admin.id),
        ip=_ip(request), commit=False,
    )
    await session.commit()
    return {"ok": True, "enabled": False}


class PasswordChange(BaseModel):
    current_password: str = Field(..., max_length=256)  # FIX: AUDIT13-L18
    new_password: str = Field(..., max_length=256)


@router.post("/password")
async def change_password(
    req: PasswordChange,
    response: Response,
    request: Request,
    admin: AdminUser = Depends(current_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Change the signed-in admin's OWN password. Verifies the current password
    (proves possession), stores the new one as argon2id, and bumps token_version so
    every session — including this one — is revoked and the admin re-logs in.
    Audited as a security event (passwords are never put in the audit record)."""
    if not verify_password(req.current_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="current_password_invalid")
    new = (req.new_password or "").strip()
    if len(new) < 8:
        raise HTTPException(status_code=400, detail="new password must be at least 8 characters")
    if verify_password(new, admin.password_hash):
        raise HTTPException(status_code=400, detail="new password must differ from the current one")
    admin.password_hash = hash_password(new)
    admin.token_version += 1  # revoke all existing sessions → re-login required
    _clear_session_cookies(response)
    # FIX: M5 - audit + commit atomically (was: commit before audit → audit trail
    # could be lost if the audit INSERT failed).
    await audit(
        session, admin_id=admin.id, action="auth.password_change",
        target_type="admin", target_id=str(admin.id), ip=_ip(request), commit=False,
    )
    await session.commit()
    return {"ok": True, "relogin_required": True}


# ---------- Security Center ----------
# Audit actions that count as "security-relevant" for the page's events feed +
# last-security-change signal. Matched as SQL prefixes/substrings (ilike).
_SEC_ACTION_LIKE = (
    "auth.%", "admin.%", "provider.key%", "flag.%", "gate.%", "moderation%",
    "maintenance.backup", "maintenance.cache%", "%2fa%", "%login%", "%password%",
)


def _mfa_required_roles() -> list[str]:
    return [r.strip() for r in settings.mfa_required_roles.split(",") if r.strip()]


@router.get("/security")
async def security_overview(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Read-only security posture for the Security Center (ТЗ §8). Everything here is
    derived from REAL state: the current admin's account, org-wide AdminUser
    aggregates, the deploy's auth policy (config), and recent security events from the
    audit log. A weighted score + recommendations are computed from those signals.

    No new tables: sessions are stateless JWTs (token_version is the revoke-all
    lever), and login/device history is not yet persisted — those areas are reported
    honestly rather than faked."""
    mfa_roles = _mfa_required_roles()

    # --- org aggregates over admin_users ---
    role_rows = (await session.execute(
        select(AdminUser.role, func.count()).group_by(AdminUser.role)
    )).all()
    by_role = {r: int(n) for r, n in role_rows}
    admins_total = int(await session.scalar(select(func.count()).select_from(AdminUser)) or 0)
    active = int(await session.scalar(
        select(func.count()).select_from(AdminUser).where(AdminUser.is_active.is_(True))) or 0)
    with_2fa = int(await session.scalar(
        select(func.count()).select_from(AdminUser).where(AdminUser.totp_secret.is_not(None))) or 0)
    missing_required_2fa = 0
    if mfa_roles:
        missing_required_2fa = int(await session.scalar(
            select(func.count()).select_from(AdminUser).where(
                AdminUser.role.in_(mfa_roles),
                AdminUser.totp_secret.is_(None),
                AdminUser.is_active.is_(True),
            )) or 0)

    # --- auth policy (deploy config) ---
    ip_list = [ip.strip() for ip in settings.admin_ip_allowlist.split(",") if ip.strip()]
    jwt_default = settings.admin_jwt_secret == "change-me-in-prod"
    secure_cookies = settings.env not in ("dev", "test")
    policy = {
        "ip_allowlist_configured": bool(ip_list),
        "ip_allowlist_count": len(ip_list),
        "mfa_required_roles": mfa_roles,
        "enc_secret_configured": bool(settings.enc_secret),
        "jwt_secret_default": jwt_default,
        "secure_cookies": secure_cookies,
        "password_algo": "argon2id",
        "cookie": {"httponly": True, "samesite": "strict", "secure": secure_cookies},
        "access_ttl_minutes": int(ACCESS_TTL.total_seconds() // 60),
        "env": settings.env,
    }

    # --- recent security events (from audit log) ---
    sec_filter = or_(*[AdminAuditLog.action.ilike(p) for p in _SEC_ACTION_LIKE])
    ev_rows = (await session.scalars(
        select(AdminAuditLog).where(sec_filter)
        .order_by(AdminAuditLog.id.desc()).limit(15)
    )).all()
    ids = {e.admin_id for e in ev_rows}
    directory = {}
    if ids:
        directory = {
            aid: email for aid, email in (await session.execute(
                select(AdminUser.id, AdminUser.email).where(AdminUser.id.in_(ids))
            )).all()
        }
    events = [
        {"id": e.id, "action": e.action, "admin_id": e.admin_id,
         "admin_email": directory.get(e.admin_id), "target_type": e.target_type,
         "target_id": e.target_id, "ip": e.ip, "created_at": e.created_at.isoformat()}
        for e in ev_rows
    ]
    last_security_event_at = events[0]["created_at"] if events else None

    self_2fa = bool(admin.totp_secret)
    self_required = mfa_required(admin.role)

    # --- weighted score from real signals ---
    checks = [
        {"id": "self_2fa", "label": "2FA включена для вашего аккаунта",
         "ok": self_2fa, "weight": 25,
         "rec": "Включите TOTP/Authenticator для своего аккаунта."},
        {"id": "org_2fa", "label": "Все аккаунты с обязательной 2FA её включили",
         "ok": missing_required_2fa == 0, "weight": 20,
         "rec": f"{missing_required_2fa} админ(ов) с обязательной 2FA её не включили."},
        {"id": "jwt_secret", "label": "JWT-секрет изменён с дефолтного",
         "ok": not jwt_default, "weight": 15,
         "rec": "Задайте сильный ADMIN_JWT_SECRET (сейчас дефолтный)."},
        {"id": "enc_secret", "label": "Шифрование секретов настроено (ENC_SECRET)",
         "ok": bool(settings.enc_secret), "weight": 15,
         "rec": "Задайте отдельный ENC_SECRET для шифрования хранимых ключей."},
        {"id": "ip_allowlist", "label": "IP-allowlist админки настроен",
         "ok": bool(ip_list), "weight": 15,
         "rec": "Ограничьте доступ к админке по IP (ADMIN_IP_ALLOWLIST)."},
        {"id": "secure_cookies", "label": "Cookie помечены Secure (HTTPS)",
         "ok": secure_cookies, "weight": 10,
         "rec": "В проде куки должны быть Secure (env ≠ dev/test, доступ по HTTPS)."},
    ]
    score = sum(c["weight"] for c in checks if c["ok"])
    recommendations = [{"id": c["id"], "text": c["rec"]} for c in checks if not c["ok"]]

    return {
        "self": {
            "id": admin.id, "email": admin.email, "role": admin.role,
            "role_rank": ROLE_RANK.get(admin.role, 0),
            "is_active": admin.is_active, "has_2fa": self_2fa,
            "mfa_required": self_required,
            "last_login": admin.last_login.isoformat() if admin.last_login else None,
            "created_at": admin.created_at.isoformat() if admin.created_at else None,
            "updated_at": admin.updated_at.isoformat() if admin.updated_at else None,
            "token_version": admin.token_version,
        },
        "org": {
            "admins_total": admins_total, "active": active,
            "with_2fa": with_2fa, "without_2fa": admins_total - with_2fa,
            "by_role": by_role, "missing_required_2fa": missing_required_2fa,
        },
        "policy": policy,
        "score": score,
        "checks": checks,
        "recommendations": recommendations,
        "events": events,
        "last_security_event_at": last_security_event_at,
    }


@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    admin: AdminUser = Depends(current_admin_enrolling),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Server-side revocation: bump token_version so every previously-issued
    access/refresh token for this admin is immediately rejected, and clear the
    httpOnly access cookie on the client. Audited as a security event (this is the
    'revoke all sessions' lever surfaced by the Security Center)."""
    admin.token_version += 1
    _clear_session_cookies(response)
    # FIX: M6 - audit + commit atomically (was: commit before audit).
    await audit(
        session, admin_id=admin.id, action="auth.logout",
        target_type="admin", target_id=str(admin.id),
        after={"reason": "revoke_all_sessions"}, ip=_ip(request), commit=False,
    )
    await session.commit()
    return {"ok": True}
