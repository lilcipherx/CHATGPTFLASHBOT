"""Live localization overrides — any bot text string editable from the admin panel
without a redeploy (ТЗ §8 «Редактор локализации»).

Mirrors the pricing engine: overrides live in the `pricing` KV table under the key
``text_overrides`` and are Redis-cached for a few seconds. The shape is a nested map
``{locale: {key: text}}`` — a per-(locale, key) override of the static message dicts
in ``core.i18n.locales``.

Cross-process note: the bot / API / workers are separate processes and the translator
``t(key, locale)`` is called SYNCHRONOUSLY in handlers, so it can't await the DB/Redis.
Instead this module keeps a process-local snapshot (``_SNAPSHOT``) that the translator
reads synchronously; the snapshot is filled at startup via ``load_once()`` and kept
fresh by ``refresh_loop()`` (same pattern as ``provider_keys``). The API process also
refreshes the snapshot immediately on every write so a change shows up at once there.

With NO overrides stored the snapshot is an empty dict and the translator falls back to
the static message dicts, so default rendering is byte-identical to today.
"""
from __future__ import annotations

import asyncio
import json

from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import SUPPORTED_LOCALES
from core.db import SessionFactory
from core.models import Pricing
from core.redis_client import redis_client

KEY = "text_overrides"
_CACHE_KEY = "cache:text_overrides"
_CACHE_TTL = 10  # seconds — same best-effort TTL as pricing

# Process-local snapshot the synchronous translator reads. Refreshed from DB/Redis by
# load_once()/refresh_loop(); empty until then (=> static-dict fallback, no behaviour
# change). Shape: {locale: {key: text}}.
_SNAPSHOT: dict[str, dict[str, str]] = {}


def _clean(raw: dict) -> dict[str, dict[str, str]]:
    """Coerce a stored blob into the {locale: {key: text}} shape, dropping anything
    malformed so a bad write can never break the translator."""
    out: dict[str, dict[str, str]] = {}
    for locale, keys in (raw or {}).items():
        if locale not in SUPPORTED_LOCALES or not isinstance(keys, dict):
            continue
        bucket: dict[str, str] = {}
        for k, v in keys.items():
            if isinstance(k, str) and isinstance(v, str) and v != "":
                bucket[k] = v
        if bucket:
            out[locale] = bucket
    return out


async def _load_raw(session: AsyncSession) -> dict:
    row = await session.get(Pricing, KEY)
    return dict(row.value or {}) if row else {}


async def _save_raw(session: AsyncSession, stored: dict) -> None:
    row = await session.get(Pricing, KEY)
    if row is None:
        session.add(Pricing(key=KEY, value=stored))
    else:
        row.value = stored
    await session.commit()


async def get_overrides(session: AsyncSession) -> dict[str, dict[str, str]]:
    """Full {locale: {key: text}} override map (Redis-cached, best-effort)."""
    try:
        cached = await redis_client.get(_CACHE_KEY)
        if cached:
            return _clean(json.loads(cached))
    except Exception:  # noqa: BLE001 — cache is best-effort
        pass
    try:
        raw = await _load_raw(session)
    except Exception:  # noqa: BLE001 — pricing table absent (pre-migration) -> none
        raw = {}
    cleaned = _clean(raw)
    try:
        await redis_client.set(_CACHE_KEY, json.dumps(cleaned), ex=_CACHE_TTL)
    except Exception:  # noqa: BLE001
        pass
    return cleaned


async def set_override(session: AsyncSession, locale: str, key: str, text: str) -> None:
    """Store an override for (locale, key) and invalidate the cache. Raises
    ValueError for an unsupported locale or a blank key."""
    if locale not in SUPPORTED_LOCALES:
        raise ValueError(f"unsupported locale: {locale}")
    if not key or not key.strip():
        raise ValueError("key is required")
    raw = await _load_raw(session)
    bucket = dict(raw.get(locale) or {})
    bucket[key] = text
    raw[locale] = bucket
    await _save_raw(session, raw)
    await _invalidate()


async def clear_override(session: AsyncSession, locale: str, key: str) -> bool:
    """Remove an override (revert to the static message). Returns whether one
    existed. Invalidates the cache."""
    raw = await _load_raw(session)
    bucket = dict(raw.get(locale) or {})
    existed = key in bucket
    if existed:
        del bucket[key]
        if bucket:
            raw[locale] = bucket
        else:
            raw.pop(locale, None)
        await _save_raw(session, raw)
        await _invalidate()
    return existed


async def _invalidate() -> None:
    """Drop the Redis cache and refresh the in-process snapshot so a write applies
    live in THIS process immediately."""
    try:
        await redis_client.delete(_CACHE_KEY)
    except Exception as exc:  # noqa: BLE001
        import structlog
        structlog.get_logger().warning(
            'core.services.i18n_overrides._invalidate_failed', error=str(exc))
        # FIX: AUDIT12-L1 - was silent except: pass
    await load_once()


def lookup(locale: str, key: str) -> str | None:
    """Synchronous (locale, key) override lookup from the process-local snapshot.
    Returns None when there is no override — the translator then uses the static
    dict. Safe to call from synchronous handler code."""
    return _SNAPSHOT.get(locale, {}).get(key)


def snapshot() -> dict[str, dict[str, str]]:
    """Current in-memory override snapshot (read-only view, for tests/diagnostics)."""
    return _SNAPSHOT


async def load_once() -> None:
    """Fill the process-local snapshot from DB/Redis (best-effort — never blocks
    boot)."""
    global _SNAPSHOT
    try:
        async with SessionFactory() as session:
            _SNAPSHOT = await get_overrides(session)
    except Exception:  # noqa: BLE001 — missing table/DB at boot must not crash
        pass


async def refresh_loop(interval: int = 30) -> None:
    """Periodically refresh the snapshot so an override set in admin reaches this
    process (e.g. the bot) within seconds without a restart. Runs forever."""
    while True:
        await asyncio.sleep(interval)
        await load_once()
