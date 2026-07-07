"""Hardening fixes from the project bug-hunt: the Mini App dev-bypass must fail
closed on a public deploy, and the AI base_url SSRF guard must block hostnames that
RESOLVE to an internal address (not just literal internal IPs)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.admin.ai_routing import _validate_base_url
from api.deps import _dev_bypass_enabled
from core.config import settings


def test_dev_bypass_off_on_public_deploy(monkeypatch):
    monkeypatch.setattr(settings, "dev_webapp_bypass", True)
    monkeypatch.setattr(settings, "env", "dev")
    # Not a public deploy → bypass is allowed (local dev).
    monkeypatch.setattr(settings, "bot_mode", "polling")
    monkeypatch.setattr(settings, "webhook_base_url", "")
    assert _dev_bypass_enabled() is True
    # A public webhook deploy → bypass MUST be forced off even with the flag + dev env.
    monkeypatch.setattr(settings, "bot_mode", "webhook")
    monkeypatch.setattr(settings, "webhook_base_url", "https://bot.example.com")
    assert _dev_bypass_enabled() is False


def test_base_url_blocks_hostname_resolving_to_loopback(monkeypatch):
    monkeypatch.setattr(settings, "ai_base_url_allowlist", "")
    # 'localhost' resolves to 127.0.0.1 with no network — the literal-IP check used to
    # miss this because the host isn't a literal IP.
    with pytest.raises(HTTPException):
        _validate_base_url("http://localhost:4000/v1")


def test_base_url_blocks_literal_internal_ip(monkeypatch):
    monkeypatch.setattr(settings, "ai_base_url_allowlist", "")
    with pytest.raises(HTTPException):
        _validate_base_url("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(HTTPException):
        _validate_base_url("http://127.0.0.1:8000/")


def test_base_url_allows_normal_host(monkeypatch):
    import ipaddress

    from api.admin import ai_routing
    monkeypatch.setattr(settings, "ai_base_url_allowlist", "")
    # FIX: AUDIT-TEST - FIX: N6 made the SSRF guard fail CLOSED on unresolvable hosts
    # (the old "fall through to allowed" was an SSRF hole). Stub DNS to a PUBLIC IP so
    # this exercises the allow-path: a host resolving to a public address passes.
    monkeypatch.setattr(
        ai_routing, "_resolve_host_candidates",
        lambda host: [ipaddress.ip_address("93.184.216.34")],
    )
    assert _validate_base_url("https://gw.example/v1/") == "https://gw.example/v1"


def test_base_url_rejects_non_http_scheme(monkeypatch):
    monkeypatch.setattr(settings, "ai_base_url_allowlist", "")
    with pytest.raises(HTTPException):
        _validate_base_url("file:///etc/passwd")
