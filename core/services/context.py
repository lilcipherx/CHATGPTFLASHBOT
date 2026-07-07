"""Rolling conversation context stored in Redis (§3.2).

Key: context:{user_id} -> JSON list of {"q":..., "a":...}. The original keeps
roughly the last 1 Q&A pair; we keep it configurable. /deletecontext = DEL.
"""
from __future__ import annotations

import json

from core.config import settings
from core.redis_client import redis_client

# How many recent Q&A pairs to keep as rolling context (admin-tunable via config).
MAX_PAIRS = max(1, settings.chat_context_pairs)
TTL_SECONDS = 60 * 60 * 24  # 24h safety expiry


def _key(user_id: int, bot_id: int = 0) -> str:
    # FIX: FINAL-3 - include bot_id so multi-bot setups don't bleed context.
    return f"context:{bot_id}:{user_id}"


async def get_context(user_id: int, bot_id: int = 0) -> list[dict]:
    raw = await redis_client.get(_key(user_id, bot_id))
    return json.loads(raw) if raw else []


async def append_context(
    user_id: int, question: str, answer: str, max_pairs: int | None = None,
    bot_id: int = 0,
) -> None:
    """Push newest Q&A pair, trim to the N most-recent (N=max_pairs, default MAX_PAIRS).
    max_pairs is admin-tunable (§3.2 chat memory window); kept optional so existing
    callers retain the old single-default behaviour."""
    cap = MAX_PAIRS if max_pairs is None else max(1, max_pairs)
    pairs = await get_context(user_id, bot_id)
    pairs.append({"q": question, "a": answer})
    pairs = pairs[-cap:]
    await redis_client.set(_key(user_id, bot_id), json.dumps(pairs), ex=TTL_SECONDS)


async def clear_context(user_id: int, bot_id: int = 0) -> None:
    await redis_client.delete(_key(user_id, bot_id))


# ----- Active document (Premium doc Q&A, §5.1) -----
DOC_TTL = 60 * 60 * 2  # 2h


def _doc_key(user_id: int, bot_id: int = 0) -> str:
    # FIX: FINAL-3 - include bot_id for multi-bot isolation.
    return f"doc:{bot_id}:{user_id}"


async def set_document(user_id: int, filename: str, text: str, bot_id: int = 0) -> None:
    await redis_client.set(
        _doc_key(user_id, bot_id), json.dumps({"name": filename, "text": text}), ex=DOC_TTL
    )


async def get_document(user_id: int, bot_id: int = 0) -> dict | None:
    raw = await redis_client.get(_doc_key(user_id, bot_id))
    return json.loads(raw) if raw else None


async def clear_document(user_id: int, bot_id: int = 0) -> None:
    await redis_client.delete(_doc_key(user_id, bot_id))


# ----- Full reply text (for translate/voice on a chunked, multi-message reply) -----
# A long AI reply is delivered as several messages; the action buttons sit on the
# LAST one. To let "translate"/"voice" act on the WHOLE answer (not just the final
# chunk), we stash the full text under that last message's id. Best-effort + short
# TTL — purely an enhancement, never required for the reply itself.
REPLY_TTL = 60 * 60  # 1h


def _reply_key(chat_id: int, message_id: int) -> str:
    return f"reply:{chat_id}:{message_id}"


async def set_full_reply(chat_id: int, message_id: int, text: str) -> None:
    try:
        await redis_client.set(_reply_key(chat_id, message_id), text, ex=REPLY_TTL)
    except Exception:  # noqa: BLE001 — a cache miss must never break sending the reply
        pass


async def get_full_reply(chat_id: int, message_id: int) -> str | None:
    try:
        return await redis_client.get(_reply_key(chat_id, message_id))
    except Exception:  # noqa: BLE001
        return None
