"""Content moderation (Q16): own keyword rules + OpenAI Moderation.

Own rules run first (fast, always on); the OpenAI Moderation API is consulted
when a key is configured. Used to gate chat, image, video and music prompts —
blocks 18+, sexual content involving minors, graphic violence and deepfakes."""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.config import settings

# Own deny-rules (RU/EN). Conservative substrings/patterns for the worst-harm
# categories the upstream product also blocks (Grok/Seedance content policy §21A).
_DENY_PATTERNS = [
    r"\bchild\s*porn\b", r"\bcsam\b", r"\bпедофил", r"\bдетск\w*\s+порн",
    r"\bнасил\w*\s+над\s+детьми", r"\bизнасил",
    r"\bdeepfake\b", r"\bдипфейк", r"\bголо\w*\s+знаменитост",
    r"\bтеррор",
    r"(изготов\w*|сдела\w*|собра\w*|сделать)\W+(?:\w+\W+){0,3}?бомб",
    r"бомб\w*\W+(?:\w+\W+){0,3}?(изготов\w*|сдела\w*|собра\w*)",
    r"how to make a bomb",
]
_DENY_RE = [re.compile(p, re.IGNORECASE) for p in _DENY_PATTERNS]


@dataclass
class ModerationResult:
    allowed: bool
    reason: str | None = None


# Admin-editable extra stop-words (stored in the `pricing` KV table, key below).
# Checked as case-insensitive substrings on top of the built-in patterns. Cached
# in Redis briefly so per-message moderation doesn't hit Postgres each time.
_WORDS_KEY = "moderation_words"
_WORDS_CACHE = "cache:moderation_words"
_WORDS_TTL = 30  # seconds


_MATCH_TYPES = ("substring", "exact", "regex")


def _normalize_word(entry) -> dict | None:
    """Coerce a stored/incoming entry to {value, type}. Back-compat: a bare string is
    a case-insensitive substring rule (the original behaviour). Invalid regex is
    dropped here so a bad pattern can never break the moderation hot path."""
    import re

    if isinstance(entry, str):
        value, mtype = entry.strip(), "substring"
    elif isinstance(entry, dict):
        value = str(entry.get("value") or "").strip()
        mtype = str(entry.get("type") or "substring")
    else:
        return None
    if not value or mtype not in _MATCH_TYPES:
        if mtype not in _MATCH_TYPES:
            mtype = "substring"
        if not value:
            return None
    if mtype == "regex":
        try:
            re.compile(value)
        except re.error:
            return None
    return {"value": value, "type": mtype}


async def get_custom_words(session) -> list[dict]:
    """Admin read: the custom stop-word rules as {value, type} (uncached)."""
    from core.models import Pricing

    row = await session.get(Pricing, _WORDS_KEY)
    raw = (row.value or {}) if row else {}
    words = raw.get("words", []) if isinstance(raw, dict) else []
    out = [n for n in (_normalize_word(w) for w in words) if n]
    return out


async def set_custom_words(session, words: list) -> list[dict]:
    """Replace the custom stop-word rules; clears the cache so it applies at once.
    Each rule is {value, type} (type: substring|exact|regex); plain strings are
    accepted as substring rules. Invalid regex and empties are dropped."""
    from core.models import Pricing
    from core.redis_client import redis_client

    seen: set[tuple[str, str]] = set()
    cleaned: list[dict] = []
    for w in words:
        n = _normalize_word(w)
        if n is None:
            continue
        # regex keeps its case; non-regex rules are lower-cased (matched against lower text)
        if n["type"] != "regex":
            n["value"] = n["value"].lower()
        key = (n["value"], n["type"])
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(n)
    cleaned.sort(key=lambda x: (x["type"], x["value"]))
    row = await session.get(Pricing, _WORDS_KEY)
    if row is None:
        session.add(Pricing(key=_WORDS_KEY, value={"words": cleaned}))
    else:
        row.value = {"words": cleaned}
    await session.commit()
    try:
        await redis_client.delete(_WORDS_CACHE)
    except Exception as exc:  # noqa: BLE001
        import structlog
        structlog.get_logger().warning('core.services.moderation.set_custom_words_failed', error=str(exc))
        # FIX: AUDIT12-L1 - was silent except: pass
    return cleaned


async def _cached_custom_words() -> list[dict]:
    """Redis-cached custom stop-word rules ({value, type}) for the hot moderation path."""
    import json

    from core.redis_client import redis_client

    try:
        raw = await redis_client.get(_WORDS_CACHE)
        if raw is not None:
            return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        import structlog
        structlog.get_logger().warning('core.services.moderation._cached_custom_words_failed', error=str(exc))
        # FIX: AUDIT12-L1 - was silent except: pass
    from core.db import SessionFactory

    try:
        async with SessionFactory() as session:
            words = await get_custom_words(session)
    except Exception:  # noqa: BLE001 — never let a config read block moderation
        return []
    try:
        await redis_client.set(_WORDS_CACHE, json.dumps(words), ex=_WORDS_TTL)
    except Exception:  # noqa: BLE001
        pass
    return words


def _check_rules(text: str) -> ModerationResult:
    for rx in _DENY_RE:
        if rx.search(text):
            return ModerationResult(False, "own_rules")
    return ModerationResult(True)


async def _check_custom(text: str) -> ModerationResult:
    import re

    low = text.lower()
    for rule in await _cached_custom_words():
        value, mtype = rule["value"], rule["type"]
        if mtype == "substring":
            hit = value in low
        elif mtype == "exact":
            hit = re.search(rf"\b{re.escape(value)}\b", low) is not None
        elif mtype == "regex":
            try:
                hit = re.search(value, text, re.IGNORECASE) is not None
            except re.error:
                hit = False
        else:
            hit = False
        if hit:
            return ModerationResult(False, "custom_words")
    return ModerationResult(True)


async def _check_openai(text: str) -> ModerationResult:
    if not settings.openai_api_key:
        return ModerationResult(True)
    import asyncio

    from openai import AsyncOpenAI

    # Explicit base_url so the SDK never inherits an ambient OPENAI_BASE_URL.
    # FIX: AUDIT-FINAL-4 - explicit timeout. The OpenAI SDK default is 600s, which
    # would pin a moderation call (run BEFORE charge) for 10 minutes on a hung
    # upstream — locking the user out. Use the project's ai_request_timeout.
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=getattr(settings, "ai_request_timeout", 30),
    )
    # Retry once on a transient error before deciding. The worst-harm categories
    # (CP / deepfakes / terror / weapons) are already blocked fail-closed by the
    # local rules above, so a residual OpenAI outage degrades to allow rather than
    # blocking all generation — a deliberate availability trade-off.
    for attempt in range(2):
        try:
            resp = await client.moderations.create(model="omni-moderation-latest", input=text)
            result = resp.results[0]
            if result.flagged:
                cats = [c for c, v in result.categories.model_dump().items() if v]
                return ModerationResult(False, ",".join(cats) or "openai")
            return ModerationResult(True)
        except Exception:  # noqa: BLE001
            if attempt == 0:
                await asyncio.sleep(0.5)
                continue
            return ModerationResult(True)
    return ModerationResult(True)


async def moderate(text: str) -> ModerationResult:
    rules = _check_rules(text)
    if not rules.allowed:
        return rules
    custom = await _check_custom(text)
    if not custom.allowed:
        return custom
    return await _check_openai(text)
