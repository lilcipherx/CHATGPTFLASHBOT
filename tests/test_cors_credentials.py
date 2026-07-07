"""The admin SPA authenticates with the httpOnly `admin_access` cookie and sends
every request with ``credentials: include``. For a cross-origin admin (dev vite on
another port, or a split ``api.<domain>`` deploy) the browser will only expose the
response to JS when the server answers with ``Access-Control-Allow-Credentials:
true``. Without it the browser blocks reading the body of even a 401 — so the login
screen can't see ``otp_required`` and shows a misleading "wrong password", and every
mutation button silently fails.

Regression: ``CORSMiddleware`` was added without ``allow_credentials=True``. These
tests assert the actual response carries the credentials header for an allowed
origin, on both a simple request and a preflight.

The TestClient is used WITHOUT its context manager on purpose: that skips the app
lifespan (which would start the bot/refresh loops) — we only exercise the CORS
middleware, which wraps the app regardless of lifespan.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

ORIGIN = "http://localhost:5174"


def test_simple_request_reflects_credentials_header():
    client = TestClient(app)
    # The real admin request carries the httpOnly `admin_access` cookie (credentials:
    # include). With a cookie present, Starlette echoes the SPECIFIC origin (never "*",
    # which the browser forbids alongside credentials) + the credentials flag — which
    # is exactly what an established-session cross-origin admin call needs.
    r = client.get(
        "/health",
        headers={"Origin": ORIGIN, "Cookie": "admin_access=test"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == ORIGIN
    assert r.headers.get("access-control-allow-credentials") == "true"


def test_preflight_allows_credentialed_admin_login():
    client = TestClient(app)
    r = client.options(
        "/api/admin/auth/login",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-credentials") == "true"
    assert r.headers.get("access-control-allow-origin") == ORIGIN
