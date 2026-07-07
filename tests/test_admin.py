"""Admin auth primitives (argon2 / TOTP / JWT), RBAC hierarchy, route mounting."""
from __future__ import annotations

import pyotp

from core.services import admin_auth


def test_password_hash_roundtrip():
    h = admin_auth.hash_password("s3cret!")
    assert h != "s3cret!"
    assert admin_auth.verify_password("s3cret!", h) is True
    assert admin_auth.verify_password("wrong", h) is False


def test_totp_verify():
    secret = admin_auth.new_totp_secret()
    code = pyotp.TOTP(secret).now()
    assert admin_auth.verify_totp(secret, code) is True
    assert admin_auth.verify_totp(secret, "000000") is False


def test_jwt_roundtrip_and_type():
    token = admin_auth.create_token(7, "admin")
    payload = admin_auth.decode_token(token)
    assert payload["sub"] == "7"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"
    refresh = admin_auth.create_token(7, "admin", refresh=True)
    assert admin_auth.decode_token(refresh)["type"] == "refresh"


def test_role_hierarchy():
    assert admin_auth.role_allows("superadmin", "admin") is True
    assert admin_auth.role_allows("admin", "superadmin") is False
    assert admin_auth.role_allows("support", "support") is True
    assert admin_auth.role_allows("moderator", "admin") is False
    assert admin_auth.role_allows("admin", "support") is True  # higher rank covers support
    # support must NOT escalate to moderator-gated actions (ban / effect CRUD)
    assert admin_auth.role_allows("support", "moderator") is False
    assert admin_auth.role_allows("moderator", "support") is True  # moderator outranks support


def test_admin_routes_mounted():
    from api.main import app

    paths = {r.path for r in app.routes}
    assert "/api/admin/auth/login" in paths
    assert "/api/admin/users" in paths
    assert "/api/admin/dashboard" in paths
    assert "/api/admin/pricing/{key}" in paths
    assert "/api/admin/broadcasts" in paths
