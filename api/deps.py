"""Auth dependencies: Mini App initData (HMAC) and admin JWT (Phase 6.5)."""
from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from core.config import settings


def verify_init_data(init_data: str) -> dict:
    """Validate Telegram WebApp initData per the documented HMAC scheme and
    return the parsed user dict. Raises 401 on mismatch."""
    try:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="bad initData") from exc

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="missing hash")

    data_check = "\n".join(f"{k}={parsed[k]}" for k in sorted(parsed))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        raise HTTPException(status_code=401, detail="invalid signature")

    # Reject stale initData (replay of a leaked string). Telegram includes the
    # issue time in `auth_date` (unix seconds).
    if settings.initdata_max_age > 0:
        try:
            auth_date = int(parsed.get("auth_date", "0"))
        except ValueError:
            auth_date = 0
        if auth_date <= 0 or time.time() - auth_date > settings.initdata_max_age:
            raise HTTPException(status_code=401, detail="initData expired")

    import json

    # A real WebApp initData always carries the user object; without it the routes
    # have no identity (downstream code reads tg["id"]). Reject rather than return
    # an empty dict that would later KeyError into a 500.
    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="no user in initData")
    try:
        return json.loads(user_raw)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="bad user in initData") from exc


# Fixed identity used when opening the Mini App in a plain browser during local
# dev (no Telegram, so no signed initData). Strictly gated on ENV=dev|test.
DEV_WEBAPP_USER = {
    "id": 99999001,
    "username": "dev_tester",
    "language_code": "ru",
    "first_name": "Dev",
}


def _dev_bypass_enabled() -> bool:
    # Secure by default: the bypass only activates when explicitly opted in via
    # DEV_WEBAPP_BYPASS=true AND env is dev/test. Defence-in-depth: it is ALSO forced
    # off on a public deploy (webhook mode + webhook_base_url), so a misconfigured
    # prod that left ENV=dev and the flag on can't hand every anonymous internet client
    # the fixed DEV_WEBAPP_USER session — fail-closed, like _require_prod_secret.
    return (
        settings.dev_webapp_bypass
        and settings.env in ("dev", "test")
        and not settings.is_public_deploy
    )


async def current_webapp_user(x_init_data: str = Header(default="")) -> dict:
    if not x_init_data:
        if _dev_bypass_enabled():
            return dict(DEV_WEBAPP_USER)
        raise HTTPException(status_code=401, detail="no initData")
    try:
        return verify_init_data(x_init_data)
    except HTTPException:
        if _dev_bypass_enabled():
            return dict(DEV_WEBAPP_USER)
        raise
