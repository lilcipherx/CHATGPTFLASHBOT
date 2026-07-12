"""Unit tests for admin API dependencies (api/admin/deps.py): the IP allow-list
matcher (exact + CIDR + open + invalid), the LIKE-injection escaper, the IP gate,
and the RBAC role gate. All pure / near-pure — no DB, no live FastAPI request."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.admin import deps


# ---- _ip_matches: exact + CIDR + open + invalid ----
def test_ip_matches_exact():
    assert deps._ip_matches("1.2.3.4", {"1.2.3.4"}) is True


def test_ip_matches_cidr_in_range():
    assert deps._ip_matches("10.1.2.3", {"10.0.0.0/8"}) is True


def test_ip_matches_cidr_out_of_range():
    assert deps._ip_matches("11.1.2.3", {"10.0.0.0/8"}) is False


def test_ip_matches_open_ipv4():
    assert deps._ip_matches("203.0.113.9", {"0.0.0.0/0"}) is True


def test_ip_matches_open_ipv6():
    assert deps._ip_matches("2001:db8::1", {"::/0"}) is True


def test_ip_matches_empty_allow_rejects():
    assert deps._ip_matches("1.2.3.4", set()) is False


def test_ip_matches_invalid_client_string():
    assert deps._ip_matches("not-an-ip", {"10.0.0.0/8"}) is False


# ---- like_contains: LIKE metacharacter escaping (anti SQL-LIKE-wildcard abuse) ----
def test_like_contains_plain():
    assert deps.like_contains("bob") == "%bob%"


def test_like_contains_escapes_metacharacters():
    out = deps.like_contains("a%b_c\\d")
    # %, _ and the backslash escape char itself are all backslash-escaped so they
    # match literally; the whole term is wrapped for a substring search.
    assert out.startswith("%") and out.endswith("%")
    assert "\\%" in out and "\\_" in out and "\\\\" in out


# ---- ip_allowlisted: empty list = open (dev); a mismatch is 403 ----
@pytest.mark.asyncio
async def test_ip_allowlisted_open_when_empty(monkeypatch):
    monkeypatch.setattr(deps, "_allowlist", lambda: set())
    req = type("R", (), {"client": type("C", (), {"host": "9.9.9.9"})()})()
    assert await deps.ip_allowlisted(req) is None  # no raise


@pytest.mark.asyncio
async def test_ip_allowlisted_blocks_outsider(monkeypatch):
    monkeypatch.setattr(deps, "_allowlist", lambda: {"10.0.0.0/8"})
    req = type("R", (), {"client": type("C", (), {"host": "9.9.9.9"})()})()
    with pytest.raises(HTTPException) as ei:
        await deps.ip_allowlisted(req)
    assert ei.value.status_code == 403


# ---- require_role: RBAC gate returns admin when allowed, 403 when not ----
@pytest.mark.asyncio
async def test_require_role_allows(monkeypatch):
    monkeypatch.setattr(deps, "role_allows", lambda role, *rs: True)
    checker = deps.require_role("admin")
    admin = type("A", (), {"role": "superadmin"})()
    assert await checker(admin=admin) is admin


@pytest.mark.asyncio
async def test_require_role_rejects_lower_role(monkeypatch):
    monkeypatch.setattr(deps, "role_allows", lambda role, *rs: False)
    checker = deps.require_role("admin")
    admin = type("A", (), {"role": "support"})()
    with pytest.raises(HTTPException) as ei:
        await checker(admin=admin)
    assert ei.value.status_code == 403
