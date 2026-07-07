"""Admin-controlled feature flags (stored in the `pricing` KV table, same pattern
as providers_admin). Every toggleable behaviour the bot exposes is gated here so
the admin panel is the single switchboard.

Reads are cached in Redis for a few seconds so per-message checks (e.g. the
channel-subscription gate) don't hit Postgres on every update.
"""
from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Pricing
from core.redis_client import redis_client

KEY = "feature_flags"
_CACHE_KEY = "cache:feature_flags"
_CACHE_TTL = 10  # seconds

# flag -> (default, human label) — the admin UI renders this catalogue
# NOTE: full-product launch — every service flag defaults ON. A service generates as
# soon as its provider key is set on the admin API-keys page; without a key the
# attempt safely refunds. The admin can still turn any flag OFF (shows "скоро").
DEFAULTS: dict[str, tuple[bool, str]] = {
    "channel_gate": (True, "Гейт: обязательная подписка на канал"),
    "faceswap": (True, "Сервис: Замена лиц (нужен ключ провайдера)"),
    "upscale": (True, "Сервис: Увеличение X2/X4 (нужен ключ провайдера)"),
    "recraft": (True, "Сервис: Recraft (нужен ключ провайдера)"),
    "avatar": (True, "Сервис: Аватары 100 фото (нужен ключ провайдера)"),
    "vision": (True, "Распознавание изображений (фото в чат)"),
    "photo_edit": (True, "Редактирование фото в чате (фото+подпись → img2img)"),
    "voice_input": (True, "Голосовой ввод (voice → ответ)"),
    "voice_input_free": (False, "Голосовой ввод доступен бесплатным (иначе только Premium)"),
    "voice_output": (True, "Голосовые ответы (TTS: озвучка ответов кнопкой 🔊)"),
    "music": (True, "Генерация музыки"),
    "video": (True, "Генерация видео"),
    "documents": (True, "Сервис: Документы (Premium Q&A)"),
}


def default_flags() -> dict[str, bool]:
    return {k: v[0] for k, v in DEFAULTS.items()}


async def get_flags(session: AsyncSession) -> dict[str, bool]:
    """All flags merged over defaults (DB overrides the default)."""
    row = await session.get(Pricing, KEY)
    stored = (row.value or {}) if row else {}
    flags = default_flags()
    flags.update({k: bool(v) for k, v in stored.items() if k in DEFAULTS})
    return flags


async def is_enabled(session: AsyncSession, flag: str) -> bool:
    flags = await get_flags(session)
    return flags.get(flag, DEFAULTS.get(flag, (False,))[0])


async def set_flag(session: AsyncSession, flag: str, value: bool) -> dict[str, bool]:
    if flag not in DEFAULTS:
        raise ValueError(f"unknown flag {flag!r}")
    row = await session.get(Pricing, KEY)
    stored = dict(row.value or {}) if row else {}
    stored[flag] = bool(value)
    if row is None:
        session.add(Pricing(key=KEY, value=stored))
    else:
        row.value = stored
    await session.commit()
    await redis_client.delete(_CACHE_KEY)
    return await get_flags(session)


async def is_enabled_cached(session: AsyncSession, flag: str) -> bool:
    """Redis-cached read for hot paths (gate middleware). Falls back to DB."""
    try:
        raw = await redis_client.get(_CACHE_KEY)
        if raw:
            flags = json.loads(raw)
        else:
            flags = await get_flags(session)
            await redis_client.set(_CACHE_KEY, json.dumps(flags), ex=_CACHE_TTL)
    except Exception:  # noqa: BLE001 — never let flag-reads break a handler
        flags = await get_flags(session)
    return bool(flags.get(flag, DEFAULTS.get(flag, (False,))[0]))
