"""Mini App initData verification (api.deps.verify_init_data) — the security
boundary for every Mini App request. Confirms a valid Telegram signature passes and
that tampering / forgery / replay / missing fields are all rejected with 401."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException

from api import deps
from core.config import settings

_BOT_TOKEN = "123456:TESTTOKEN_for_initdata_verification_xxxxxxxx"
_USER = {"id": 555, "username": "neo", "language_code": "en", "first_name": "Neo"}


def _sign(params: dict[str, str], token: str = _BOT_TOKEN) -> str:
    """Build a Telegram-valid initData query string for `params` signed with `token`."""
    data_check = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**params, "hash": h})


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", _BOT_TOKEN, raising=False)
    monkeypatch.setattr(settings, "initdata_max_age", 3600, raising=False)
    # ensure the dev bypass can't mask a rejection in these tests
    monkeypatch.setattr(settings, "dev_webapp_bypass", False, raising=False)
    monkeypatch.setattr(settings, "env", "prod", raising=False)
    yield


def _params(**over) -> dict[str, str]:
    p = {"auth_date": str(int(time.time())), "user": json.dumps(_USER)}
    p.update(over)
    return p


def test_valid_signature_returns_user():
    user = deps.verify_init_data(_sign(_params()))
    assert user["id"] == 555 and user["username"] == "neo"


def test_tampered_payload_rejected():
    # sign one user, then swap the user field → hash no longer matches
    p = _params()
    signed = _sign(p)
    forged = signed.replace(
        urlencode({"user": p["user"]}), urlencode({"user": json.dumps({**_USER, "id": 1})})
    )
    with pytest.raises(HTTPException) as ei:
        deps.verify_init_data(forged)
    assert ei.value.status_code == 401


def test_wrong_token_signature_rejected():
    # signed with a DIFFERENT bot token than the server's → forgery
    forged = _sign(_params(), token="999:OTHER_BOT_TOKEN_aaaaaaaaaaaaaaaaaaaa")
    with pytest.raises(HTTPException) as ei:
        deps.verify_init_data(forged)
    assert ei.value.status_code == 401


def test_missing_hash_rejected():
    with pytest.raises(HTTPException) as ei:
        deps.verify_init_data(urlencode(_params()))  # no hash field
    assert ei.value.status_code == 401


def test_missing_user_rejected():
    p = {"auth_date": str(int(time.time()))}
    with pytest.raises(HTTPException) as ei:
        deps.verify_init_data(_sign(p))
    assert ei.value.status_code == 401


def test_expired_initdata_rejected():
    old = _params(auth_date=str(int(time.time()) - 7200))  # 2h old, max age 1h
    with pytest.raises(HTTPException) as ei:
        deps.verify_init_data(_sign(old))
    assert ei.value.status_code == 401


async def test_dev_bypass_returns_fixed_user_only_in_dev(monkeypatch):
    monkeypatch.setattr(settings, "dev_webapp_bypass", True, raising=False)
    monkeypatch.setattr(settings, "env", "dev", raising=False)
    user = await deps.current_webapp_user(x_init_data="")
    assert user["id"] == deps.DEV_WEBAPP_USER["id"]

    # …but NOT in prod, even with the flag on
    monkeypatch.setattr(settings, "env", "prod", raising=False)
    with pytest.raises(HTTPException) as ei:
        await deps.current_webapp_user(x_init_data="")
    assert ei.value.status_code == 401
