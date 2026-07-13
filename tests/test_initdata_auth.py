"""Mini App initData HMAC verification + dev-bypass gating (Loop coverage, auth-
critical). Builds initData signed with the same scheme the verifier uses; asserts the
valid path returns the user, and every tamper/replay/shape failure raises 401.
"""
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

_TOKEN = "999:testtoken"


def _init_data(fields: dict) -> str:
    data_check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", _TOKEN.encode(), hashlib.sha256).digest()
    fields = {**fields, "hash": hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()}
    return urlencode(fields)


def _valid(monkeypatch, auth_date=None) -> str:
    monkeypatch.setattr(settings, "bot_token", _TOKEN)
    return _init_data({
        "user": json.dumps({"id": 4242, "username": "u"}),
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
    })


def test_valid_init_data_returns_user(monkeypatch):
    monkeypatch.setattr(settings, "initdata_max_age", 86400)
    data = _valid(monkeypatch)
    user = deps.verify_init_data(data)
    assert user["id"] == 4242 and user["username"] == "u"


def test_tampered_hash_rejected(monkeypatch):
    monkeypatch.setattr(settings, "initdata_max_age", 86400)
    data = _valid(monkeypatch).replace("hash=", "hash=deadbeef") + ""
    # Flip the hash value to a wrong one.
    data = data.rsplit("hash=", 1)[0] + "hash=" + "0" * 64
    with pytest.raises(HTTPException) as e:
        deps.verify_init_data(data)
    assert e.value.status_code == 401


def test_missing_hash_rejected(monkeypatch):
    monkeypatch.setattr(settings, "bot_token", _TOKEN)
    with pytest.raises(HTTPException) as e:
        deps.verify_init_data(urlencode({"user": "{}", "auth_date": str(int(time.time()))}))
    assert e.value.status_code == 401


def test_stale_auth_date_rejected(monkeypatch):
    monkeypatch.setattr(settings, "initdata_max_age", 3600)
    data = _valid(monkeypatch, auth_date=int(time.time()) - 99999)
    with pytest.raises(HTTPException) as e:
        deps.verify_init_data(data)
    assert e.value.status_code == 401


def test_no_user_field_rejected(monkeypatch):
    monkeypatch.setattr(settings, "initdata_max_age", 86400)
    monkeypatch.setattr(settings, "bot_token", _TOKEN)
    # Correctly signed, but carries no `user` object → 401 (no identity).
    data = _init_data({"auth_date": str(int(time.time())), "query_id": "x"})
    with pytest.raises(HTTPException) as e:
        deps.verify_init_data(data)
    assert e.value.status_code == 401


async def test_current_webapp_user_dev_bypass(monkeypatch):
    # Fail-closed gate: bypass only when explicitly enabled + non-public dev/test.
    monkeypatch.setattr(settings, "dev_webapp_bypass", True)
    monkeypatch.setattr(settings, "env", "test")
    monkeypatch.setattr(settings, "public_deploy", False)
    monkeypatch.setattr(settings, "webhook_base_url", "")
    got = await deps.current_webapp_user(x_init_data="")
    assert got["id"] == deps.DEV_WEBAPP_USER["id"]

    # Disabled bypass → no initData is a hard 401.
    monkeypatch.setattr(settings, "dev_webapp_bypass", False)
    with pytest.raises(HTTPException) as e:
        await deps.current_webapp_user(x_init_data="")
    assert e.value.status_code == 401


async def test_current_webapp_user_bypass_on_bad_initdata(monkeypatch):
    # A malformed initData string that fails verification also falls back to the dev
    # user when the bypass is enabled (non-public dev/test).
    monkeypatch.setattr(settings, "dev_webapp_bypass", True)
    monkeypatch.setattr(settings, "env", "test")
    monkeypatch.setattr(settings, "public_deploy", False)
    monkeypatch.setattr(settings, "webhook_base_url", "")
    got = await deps.current_webapp_user(x_init_data="not-valid-initdata")
    assert got["id"] == deps.DEV_WEBAPP_USER["id"]
