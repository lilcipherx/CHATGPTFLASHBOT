"""Native provider API keys, editable from the admin panel.

The real OpenAI / Anthropic / Google / … keys can be entered in the admin UI
instead of (or on top of) the .env file. They are stored ENCRYPTED in the
`pricing` KV table and applied onto the live ``settings`` object at process
startup and on every change, so every adapter — which reads
``settings.<provider>_api_key`` at call time — transparently uses the DB value.
A key set here OVERRIDES the .env default; clearing it reverts to .env.

Cross-process note: the bot / API / workers are separate processes. The API
applies a change in-process immediately; the bot refreshes on a short interval
(see ``refresh_loop``) so a key entered in admin starts working within seconds
without a restart. Workers re-read on startup.
"""
from __future__ import annotations

import asyncio

from core.config import settings
from core.db import SessionFactory
from core.models import Pricing
from core.services.crypto import decrypt, encrypt

KEY = "provider_api_keys"

# provider name -> (Settings field, human label). `name` is the stable id used by
# the admin UI / API; `field` is the Settings attribute the value is applied to.
PROVIDERS: list[tuple[str, str, str]] = [
    ("openai", "openai_api_key", "OpenAI — GPT, изображения, TTS, распознавание речи"),
    ("anthropic", "anthropic_api_key", "Anthropic — Claude"),
    ("google", "google_api_key", "Google — Gemini"),
    ("deepseek", "deepseek_api_key", "DeepSeek"),
    ("perplexity", "perplexity_api_key", "Perplexity — поиск"),
    ("openrouter", "openrouter_api_key", "OpenRouter — шлюз моделей"),
    ("xai", "xai_api_key", "xAI — Grok"),
    ("kling", "kling_api_key", "Kling — видео"),
    ("minimax", "minimax_api_key", "MiniMax — видео"),
    ("pika", "pika_api_key", "Pika — видео"),
    ("seedream", "seedream_api_key", "Seedream — изображения"),
    ("bfl", "bfl_api_key", "Black Forest Labs — Flux"),
    ("midjourney", "midjourney_api_key", "Midjourney — изображения"),
    ("suno", "suno_api_key", "Suno — музыка"),
]

_FIELD = {name: field for name, field, _ in PROVIDERS}

# Reserved (non-provider) entries in the same KV row holding endpoint/model
# overrides. Stored in plaintext (they are an endpoint / model id, not secrets).
_BASE_URL_KEY = "_openai_base_url"
# FIX: AUDIT13-M2 - Suno base URL + model id, editable from the admin panel (parity
# with the OpenAI base URL). Lets the operator set the exact "V5.5" model without a
# redeploy; the music adapter reads settings.suno_base_url / settings.suno_model.
_SUNO_BASE_URL_KEY = "_suno_base_url"
_SUNO_MODEL_KEY = "_suno_model"

# Snapshot the .env-provided values ONCE at import (before any DB override is
# applied), so the admin UI can tell whether a key comes from .env or the DB, and
# clearing a DB key can revert to the original .env value.
_ENV_DEFAULTS: dict[str, str] = {
    field: getattr(settings, field, "") for _n, field, _l in PROVIDERS
}
_ENV_OPENAI_BASE_URL: str = getattr(settings, "openai_base_url", "")
_ENV_SUNO_BASE_URL: str = getattr(settings, "suno_base_url", "")
_ENV_SUNO_MODEL: str = getattr(settings, "suno_model", "")


def _mask(key: str) -> str:
    return f"…{key[-4:]}" if key and len(key) > 4 else ("****" if key else "")


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


async def apply_to_settings(session) -> int:
    """Decrypt stored keys and write them onto the live settings object. Returns
    how many providers got a DB key. A provider with no DB key keeps its .env
    default (we never blank an env key we didn't override)."""
    stored = await _load_raw(session)
    applied = 0
    for name, field, _label in PROVIDERS:
        enc = stored.get(name)
        plain = decrypt(enc) if enc else ""
        if plain:
            setattr(settings, field, plain)
            applied += 1
    # OpenAI base URL override (plaintext). Keep the .env default when unset.
    base = stored.get(_BASE_URL_KEY)
    if base:
        settings.openai_base_url = base
    # FIX: AUDIT13-M2 - Suno base URL + model overrides (plaintext). Keep .env default
    # when unset (never blank an env value we didn't override).
    suno_base = stored.get(_SUNO_BASE_URL_KEY)
    if suno_base:
        settings.suno_base_url = suno_base
    suno_model = stored.get(_SUNO_MODEL_KEY)
    if suno_model:
        settings.suno_model = suno_model
    return applied


async def get_suno_config(session) -> dict:
    """Current Suno base URL + model, each with whether it comes from DB or .env."""
    stored = await _load_raw(session)
    db_base = stored.get(_SUNO_BASE_URL_KEY) or ""
    db_model = stored.get(_SUNO_MODEL_KEY) or ""
    return {
        "base_url": {"value": db_base or _ENV_SUNO_BASE_URL, "source": "db" if db_base else "env"},
        "model": {"value": db_model or _ENV_SUNO_MODEL, "source": "db" if db_model else "env"},
    }


async def set_suno_config(session, base_url: str, model: str) -> dict:
    """Override (or, when blank, clear) the Suno base URL + model and apply them live."""
    stored = await _load_raw(session)
    base_url = (base_url or "").strip().rstrip("/")
    model = (model or "").strip()
    if base_url:
        stored[_SUNO_BASE_URL_KEY] = base_url
    else:
        stored.pop(_SUNO_BASE_URL_KEY, None)
    if model:
        stored[_SUNO_MODEL_KEY] = model
    else:
        stored.pop(_SUNO_MODEL_KEY, None)
    await _save_raw(session, stored)
    settings.suno_base_url = base_url or _ENV_SUNO_BASE_URL
    settings.suno_model = model or _ENV_SUNO_MODEL
    return {"base_url": settings.suno_base_url, "model": settings.suno_model}


async def get_openai_base_url(session) -> dict:
    """Current OpenAI base URL + whether it comes from the DB or .env."""
    stored = await _load_raw(session)
    db = stored.get(_BASE_URL_KEY) or ""
    return {"value": db or _ENV_OPENAI_BASE_URL, "source": "db" if db else "env"}


async def set_openai_base_url(session, url: str) -> str:
    """Override (or, when blank, clear) the OpenAI base URL and apply it live."""
    stored = await _load_raw(session)
    url = (url or "").strip().rstrip("/")
    if url:
        stored[_BASE_URL_KEY] = url
    else:
        stored.pop(_BASE_URL_KEY, None)
    await _save_raw(session, stored)
    settings.openai_base_url = url or _ENV_OPENAI_BASE_URL
    return settings.openai_base_url


async def get_status(session) -> list[dict]:
    """For the admin UI: per-provider configured flag, masked tail, and source."""
    stored = await _load_raw(session)
    out: list[dict] = []
    for name, field, label in PROVIDERS:
        db_key = decrypt(stored.get(name) or "")
        env_key = _ENV_DEFAULTS.get(field, "")
        effective = db_key or env_key
        out.append({
            "name": name,
            "label": label,
            "configured": bool(effective),
            "masked": _mask(effective),
            "source": "db" if db_key else ("env" if env_key else "none"),
        })
    return out


async def set_keys(session, updates: dict[str, str]) -> list[str]:
    """Store the given keys (encrypted) and apply them. Empty values are ignored
    (keeps the existing key, mirroring the AI-account update convention)."""
    stored = await _load_raw(session)
    changed: list[str] = []
    for name, value in updates.items():
        if name not in _FIELD or not value or not value.strip():
            continue
        stored[name] = encrypt(value.strip())
        changed.append(name)
    if changed:
        await _save_raw(session, stored)
        await apply_to_settings(session)
    return changed


async def clear_key(session, name: str) -> bool:
    """Remove a DB key and revert the live setting to its .env default."""
    if name not in _FIELD:
        return False
    stored = await _load_raw(session)
    existed = name in stored
    if existed:
        del stored[name]
        await _save_raw(session, stored)
    setattr(settings, _FIELD[name], _ENV_DEFAULTS.get(_FIELD[name], ""))
    return existed


# Cheap read-only probe per provider (validate the key actually works upstream).
# url template ({base}=current OpenAI base) + how the key is presented.
_TEST_ENDPOINTS: dict[str, tuple[str, str]] = {
    "openai": ("{base}/models", "bearer"),
    "deepseek": ("https://api.deepseek.com/models", "bearer"),
    "openrouter": ("https://openrouter.ai/api/v1/models", "bearer"),
    "xai": ("https://api.x.ai/v1/models", "bearer"),
    "anthropic": ("https://api.anthropic.com/v1/models", "anthropic"),
    "google": ("https://generativelanguage.googleapis.com/v1beta/models", "google"),
}


async def test_key(session, name: str) -> dict:
    """Probe the provider's API with its current key (DB override or .env) and return
    {ok, status_code, latency_ms, detail, supported}. Read-only — sends a cheap GET
    (the models list). Patched in tests so no network is hit."""
    import time

    import httpx

    if name not in _FIELD:
        return {"ok": False, "supported": False, "status_code": 0,
                "latency_ms": 0, "detail": "unknown provider"}
    stored = await _load_raw(session)
    key = decrypt(stored.get(name) or "") or _ENV_DEFAULTS.get(_FIELD[name], "")
    if not key:
        return {"ok": False, "supported": True, "status_code": 0,
                "latency_ms": 0, "detail": "ключ не задан"}
    spec = _TEST_ENDPOINTS.get(name)
    if spec is None:
        return {"ok": False, "supported": False, "status_code": 0, "latency_ms": 0,
                "detail": "онлайн-тест для этого провайдера пока не поддержан"}

    url_tpl, auth = spec
    base = (await get_openai_base_url(session))["value"] if name == "openai" else ""
    url = url_tpl.format(base=base.rstrip("/")) if "{base}" in url_tpl else url_tpl
    headers: dict[str, str] = {}
    params: dict[str, str] = {}
    if auth == "bearer":
        headers["Authorization"] = f"Bearer {key}"
    elif auth == "anthropic":
        headers["x-api-key"] = key
        headers["anthropic-version"] = "2023-06-01"
    elif auth == "google":
        params["key"] = key

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.get(url, headers=headers, params=params)
        ok = r.status_code < 400
        return {"ok": ok, "supported": True, "status_code": r.status_code,
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "detail": "" if ok else (r.text or "")[:200]}
    except Exception as exc:  # noqa: BLE001 — any transport error = unreachable
        return {"ok": False, "supported": True, "status_code": 0,
                "latency_ms": int((time.monotonic() - t0) * 1000), "detail": str(exc)[:200]}


async def load_once() -> None:
    """Apply DB keys at process startup (best-effort — never block boot)."""
    try:
        async with SessionFactory() as session:
            await apply_to_settings(session)
    except Exception as exc:  # noqa: BLE001 — FIX: L8 - log so a DB outage is observable
        import structlog
        structlog.get_logger().warning("provider_keys.load_failed", error=str(exc))


async def refresh_loop(interval: int = 30) -> None:
    """Periodically re-apply DB keys so a key set in admin reaches this process
    (e.g. the bot) without a restart. Runs forever; swallows transient errors."""
    while True:
        await asyncio.sleep(interval)
        try:
            async with SessionFactory() as session:
                await apply_to_settings(session)
        except Exception:  # noqa: BLE001
            pass
