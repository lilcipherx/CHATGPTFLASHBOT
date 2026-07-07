"""Payment-gateway credentials, editable from the admin panel.

Mirrors core.services.provider_keys but for the PAYMENT gateways (Stripe, YooKassa,
CryptoBot, Tribute/СБП). Each gateway's credentials can be entered in the admin UI
instead of (or on top of) the .env file. Secret fields are stored ENCRYPTED in the
`pricing` KV table; non-secret fields (e.g. a YooKassa shop id) are stored as plain
text. Values are applied onto the live ``settings`` object at process startup and on
every change, so every gateway adapter — which reads ``settings.<field>`` at call
time — transparently uses the DB value. A value set here OVERRIDES the .env default;
clearing it reverts to .env.

Telegram Stars is intentionally absent: it is native (paid through the bot token),
so it has no separate credentials to configure here.
"""
from __future__ import annotations

import asyncio

from core.config import settings
from core.db import SessionFactory
from core.models import Pricing
from core.services.crypto import decrypt, encrypt

KEY = "payment_gateway_keys"


class Field:
    __slots__ = ("field", "label", "secret")

    def __init__(self, field: str, label: str, secret: bool = True) -> None:
        self.field = field    # Settings attribute the value is applied to
        self.label = label    # human label for the admin UI
        self.secret = secret  # encrypt + mask (True) vs. plaintext + show (False)


# gateway id -> (human label, ordered fields). The id is the stable key the admin
# UI / API uses; it matches the Transaction.gateway value where applicable.
GATEWAYS: list[tuple[str, str, list[Field]]] = [
    ("stripe", "Stripe", [
        Field("stripe_secret", "Secret key (sk_live_…)"),
        Field("stripe_webhook_secret", "Webhook secret (whsec_…)"),
    ]),
    ("yookassa", "ЮКасса", [
        Field("yookassa_shop_id", "Shop ID", secret=False),
        Field("yookassa_secret", "Secret key"),
    ]),
    ("crypto", "CryptoBot (Crypto Pay)", [
        Field("crypto_pay_token", "Crypto Pay API token"),
    ]),
    ("tribute", "СБП (Tribute)", [
        Field("tribute_api_key", "API key"),
    ]),
]

# field -> Field (flat lookup) and field -> gateway id.
_FIELDS: dict[str, Field] = {f.field: f for _id, _l, fs in GATEWAYS for f in fs}
_GATEWAY_OF: dict[str, str] = {f.field: gid for gid, _l, fs in GATEWAYS for f in fs}

# Snapshot the .env-provided values ONCE at import (before any DB override), so the
# admin UI can tell whether a value is from .env or the DB, and clearing a DB value
# reverts to the original .env value.
_ENV_DEFAULTS: dict[str, str] = {f: str(getattr(settings, f, "") or "") for f in _FIELDS}


def _mask(value: str) -> str:
    return f"…{value[-4:]}" if value and len(value) > 4 else ("****" if value else "")


async def _load_raw(session) -> dict[str, str]:
    row = await session.get(Pricing, KEY)
    return dict(row.value or {}) if row else {}


async def _save_raw(session, stored: dict[str, str]) -> None:
    row = await session.get(Pricing, KEY)
    if row is None:
        session.add(Pricing(key=KEY, value=stored))
    else:
        row.value = stored
    await session.commit()


def _decode(field: str, raw: str) -> str:
    """Decode a stored value: secret fields are encrypted, others are plaintext."""
    if not raw:
        return ""
    return decrypt(raw) if _FIELDS[field].secret else raw


async def apply_to_settings(session) -> int:
    """Decrypt/read stored values and write them onto the live settings object.
    Returns how many fields got a DB value. A field with no DB value keeps its .env
    default (we never blank an env value we didn't override)."""
    stored = await _load_raw(session)
    applied = 0
    for field in _FIELDS:
        plain = _decode(field, stored.get(field, ""))
        if plain:
            setattr(settings, field, plain)
            applied += 1
    return applied


async def get_status(session) -> list[dict]:
    """For the admin UI: per-gateway field status (configured flag, masked/visible
    value, source). Secrets are masked; non-secret fields show their full value."""
    stored = await _load_raw(session)
    out: list[dict] = []
    for gid, label, fields in GATEWAYS:
        field_status = []
        for f in fields:
            db_val = _decode(f.field, stored.get(f.field, ""))
            env_val = _ENV_DEFAULTS.get(f.field, "")
            effective = db_val or env_val
            field_status.append({
                "field": f.field,
                "label": f.label,
                "secret": f.secret,
                "configured": bool(effective),
                "value": _mask(effective) if f.secret else effective,
                "source": "db" if db_val else ("env" if env_val else "none"),
            })
        out.append({
            "id": gid,
            "label": label,
            "fields": field_status,
            # The gateway is "ready" once every field has an effective value.
            "ready": all(fs["configured"] for fs in field_status),
        })
    return out


async def set_fields(session, updates: dict[str, str]) -> list[str]:
    """Store the given field values (secrets encrypted) and apply them live. Empty
    values are ignored (keeps the existing value, mirroring provider_keys)."""
    stored = await _load_raw(session)
    changed: list[str] = []
    for field, value in updates.items():
        if field not in _FIELDS or value is None or not str(value).strip():
            continue
        v = str(value).strip()
        stored[field] = encrypt(v) if _FIELDS[field].secret else v
        changed.append(field)
    if changed:
        await _save_raw(session, stored)
        await apply_to_settings(session)
    return changed


async def clear_field(session, field: str) -> bool:
    """Remove a DB value and revert the live setting to its .env default."""
    if field not in _FIELDS:
        return False
    stored = await _load_raw(session)
    existed = field in stored
    if existed:
        del stored[field]
        await _save_raw(session, stored)
    setattr(settings, field, _ENV_DEFAULTS.get(field, ""))
    return existed


async def load_once() -> None:
    """Apply DB values at process startup (best-effort — never block boot)."""
    try:
        async with SessionFactory() as session:
            await apply_to_settings(session)
    except Exception:  # noqa: BLE001 — missing table/DB at boot must not crash
        pass


async def refresh_loop(interval: int = 30) -> None:
    """Periodically re-apply DB values so a credential set in admin reaches this
    process without a restart. Runs forever; swallows transient errors."""
    while True:
        await asyncio.sleep(interval)
        try:
            async with SessionFactory() as session:
                await apply_to_settings(session)
        except Exception:  # noqa: BLE001
            pass
