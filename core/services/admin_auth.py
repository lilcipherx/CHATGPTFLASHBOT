"""Admin authentication primitives: argon2 passwords, TOTP 2FA, JWT sessions,
RBAC role hierarchy (§11A.1)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from core.config import settings

_ph = PasswordHasher()

ACCESS_TTL = timedelta(minutes=30)
REFRESH_TTL = timedelta(days=7)
ALGO = "HS256"

# role -> rank (strict hierarchy). support and moderator are DISTINCT ranks so a
# support operator cannot reach moderator-gated actions (ban / effect CRUD) and
# vice-versa; a role only satisfies a requirement of equal-or-lower rank, or an
# exact role match (see role_allows).
ROLE_RANK = {"support": 1, "moderator": 2, "admin": 3, "superadmin": 4}


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


# Precomputed argon2 hash of a throwaway password. The login path verifies the
# supplied password against THIS whenever there is no real hash to check (the
# email doesn't exist, or the account is inactive), so an unknown/disabled email
# costs the same argon2 time as a real wrong-password attempt. Without it the
# `or`-short-circuit skips argon2 for unknown emails, turning response latency
# into a user-enumeration oracle for which admin accounts exist.
_DUMMY_HASH = _ph.hash("argon2-login-timing-equalizer")


def verify_password_dummy(password: str) -> None:
    """Spend argon2 verification time without a real hash, to equalize login
    latency for unknown/inactive accounts. The result is intentionally discarded."""
    try:
        _ph.verify(_DUMMY_HASH, password)
    except Exception:  # noqa: BLE001 — only the time spent matters, not the outcome
        pass


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.brand_name)


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def create_token(
    admin_id: int,
    role: str,
    *,
    refresh: bool = False,
    ver: int = 0,
    scope: str = "full",
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(admin_id),
        "role": role,
        "type": "refresh" if refresh else "access",
        "ver": ver,  # token-version; revoked when AdminUser.token_version changes
        "scope": scope,  # "full" or "mfa_setup" (restricted to 2FA enrollment)
        "iat": now,
        "exp": now + (REFRESH_TTL if refresh else ACCESS_TTL),
    }
    return jwt.encode(payload, settings.admin_jwt_secret, algorithm=ALGO)


def decode_token(token: str) -> dict:
    # FIX: AUDIT-16 - add leeway for clock skew in multi-replica deploys
    return jwt.decode(token, settings.admin_jwt_secret, algorithms=[ALGO], leeway=10)


def mfa_required(role: str) -> bool:
    """True if this role must have 2FA enrolled (§8). Driven by config so the set
    can be tightened (e.g. add "moderator") without code changes."""
    roles = {r.strip() for r in settings.mfa_required_roles.split(",") if r.strip()}
    return role in roles


def role_allows(role: str, *required: str) -> bool:
    """True if `role` exactly matches one of the required roles, or outranks it
    (strictly higher rank). support(1) < moderator(2) < admin(3) < superadmin(4),
    so support no longer satisfies a moderator requirement."""
    have = ROLE_RANK.get(role, 0)
    if role in required:
        return True
    return any(have >= ROLE_RANK.get(r, 99) for r in required)
