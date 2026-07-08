"""Model→adapter routing + the single `chat()` entrypoint used by handlers.

Maps the bot's logical model keys (constants.TEXT_MODELS) to a concrete provider
instance and that provider's real API model id. When the chosen provider has no
key configured, falls back to any available provider so dev/demo still works;
if nothing is available, returns a clear "service unavailable" message.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from core.ai_router.anthropic_adapter import anthropic_text
from core.ai_router.base import Message, ProviderUnavailable, TextProvider, TextResult
from core.ai_router.google_adapter import google_text
from core.ai_router.openai_adapter import (
    OpenAICompatibleText,
    deepseek_text,
    openai_text,
    openrouter_text,
)
from core.config import settings

# Upstream errors that mean "this account is out" (rate-limited / no credits /
# bad key) — the router sidelines the account and tries the next one.
_EXHAUSTED_STATUSES = {401, 402, 403, 429}


# FIX: H8 - strip partial API keys from provider error strings before persisting to
# AIAccount.last_error. OpenAI AuthenticationError messages contain masked-but-
# partial keys like "sk-proj-***...***." — this redacts them fully.
# FIX: AUDIT12-25 - extend regex to catch ALL provider key formats, not just OpenAI.
import re as _re
# FIX: SKILL-S1 - the previous regex `sk-[A-Za-z0-9_\-]{6,}` did NOT match the
# masked-key format "sk-proj-***...***." because `*` is not in the char class,
# so the regex stopped at "sk-proj-" and left "***...***." visible. The fix:
# match "sk-" + any non-whitespace chars (6+), so masked formats are fully
# redacted. Also catches Bearer token leaks in Authorization headers.
_KEY_RE = _re.compile(
    r"(?:"
    # OpenAI keys: sk-... (including masked sk-proj-***...***.)
    r"sk-\S{6,}"
    # Anthropic: sk-ant-...
    r"|sk-ant-\S{6,}"
    # OpenRouter: sk-or-...
    r"|sk-or-\S{6,}"
    # Google: AIza... (20+ alphanumeric chars)
    r"|AIza[A-Za-z0-9_\-]{20,}"
    # (misc) cr_... keys
    r"|cr_[A-Za-z0-9_\-]{6,}"
    # Bearer token in Authorization header (catches "Bearer sk-..." leaks)
    r"|Bearer\s+\S{6,}"
    r")"
)


def _sanitize_exc(exc: Exception) -> str:
    """Redact API-key-like substrings from an exception's string representation."""
    return _KEY_RE.sub("***", str(exc))


# FIX: F26 - robust HTTP-status extraction across SDK families. OpenAI/Anthropic SDKs
# expose `.status_code`; google-genai exposes `.status` (int) or `.code`; httpx raises
# HTTPStatusError with `.response.status_code`. The old `getattr(exc, "status_code")`
# missed Google 429s, so they were never retried and were misclassified as
# "ai.unavailable" instead of "ai.rate_limit". Mirrors media_dispatch._status_code.
def _status_code(exc: Exception) -> int | None:
    code = getattr(exc, "status_code", None)
    if code is None:
        code = getattr(exc, "status", None)
    if code is None:
        code = getattr(exc, "code", None)
    if code is None:
        resp = getattr(exc, "response", None)
        code = getattr(resp, "status_code", None)
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return None

# Transient upstream failures worth a quick retry BEFORE we sideline the account
# or show the user a "try later" notice: 429 (rate-limited — usually clears in
# under a second) and 5xx (provider hiccup). Permanent per-account failures
# (401/402/403 = bad key / no credits) are deliberately NOT retried — that account
# won't recover this turn, so we fail it fast and move to the next one.
_RETRY_STATUSES = {429, 500, 502, 503, 504}
# Backoff before each *retry* (so 2 retries = up to 3 attempts total). Kept short:
# the user is waiting on a live chat turn, not a background job.
_RETRY_BACKOFFS = (0.6, 1.6)

# logical model key -> (provider instance factory, real provider model id)
_TEXT_ROUTES: dict[str, tuple[TextProvider, str]] = {}

# OpenRouter routing. When the key is FUNDED (openrouter_free_tier=False) each
# logical model maps to its real paid OpenRouter id, so the user gets the model
# they picked. When the key is FREE-TIER (openrouter_free_tier=True) everything is
# routed to one free model to avoid 402s — and quota.consume_text forces the cost
# to 1 in that mode so nobody is over-charged for a "top" model they don't get.
_FREE_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
_OPENROUTER_PAID_MODELS = {
    "gpt_5_5": "openai/gpt-4o",                       # FIX: N1 - real OpenRouter id
    "gpt_5_4": "openai/gpt-4o-mini",                  # FIX: N1 - real OpenRouter id
    "gpt_5_mini": "openai/gpt-4o-mini",               # FIX: N1 - real OpenRouter id
    "claude_4_8_opus": "anthropic/claude-3-5-sonnet", # FIX: N1 - real Anthropic id
    "claude_4_6_sonnet": "anthropic/claude-3-5-haiku",# FIX: N1 - real Anthropic id
    "deepseek_v4_pro": "deepseek/deepseek-r1",        # unchanged (already real)
    "deepseek_v4": "deepseek/deepseek-chat",          # unchanged (already real)
    "gemini_3_5_flash": "google/gemini-1.5-flash",    # FIX: N1 - real Google id
    "gemini_3_1_flash": "google/gemini-1.5-pro",      # FIX: N1 - real Google id
}


def routing_is_free_tier() -> bool:
    """True when text generation is served by the free-tier OpenRouter fallback,
    so callers (quota) can avoid over-charging for a model the user won't get."""
    return bool(settings.openrouter_api_key and settings.openrouter_free_tier)


def _build_routes() -> None:
    if _TEXT_ROUTES:
        return
    if settings.openrouter_api_key:
        orr = openrouter_text()
        if settings.openrouter_free_tier:
            _TEXT_ROUTES.update(
                {k: (orr, _FREE_MODEL) for k in _OPENROUTER_PAID_MODELS}
            )
        else:
            _TEXT_ROUTES.update(
                {k: (orr, v) for k, v in _OPENROUTER_PAID_MODELS.items()}
            )
        return
    oa = openai_text()
    an = anthropic_text()
    go = google_text()
    ds = deepseek_text()
    _TEXT_ROUTES.update(
        {
            # FIX: N1 - replaced fictional model ids with real provider model ids
            "gpt_5_5": (oa, "gpt-4o"),
            "gpt_5_4": (oa, "gpt-4o-mini"),
            "gpt_5_mini": (oa, "gpt-4o-mini"),
            "claude_4_8_opus": (an, "claude-3-5-sonnet-20241022"),
            "claude_4_6_sonnet": (an, "claude-3-5-haiku-20241022"),
            "deepseek_v4_pro": (ds, "deepseek-reasoner"),
            "deepseek_v4": (ds, "deepseek-chat"),
            "gemini_3_5_flash": (go, "gemini-1.5-flash"),
            "gemini_3_1_flash": (go, "gemini-1.5-pro"),
        }
    )


def provider_for(model_key: str) -> tuple[TextProvider | None, str]:
    _build_routes()
    return _TEXT_ROUTES.get(model_key, (None, model_key))


def _first_available() -> tuple[TextProvider, str] | None:
    _build_routes()
    for provider, model_id in _TEXT_ROUTES.values():
        if provider.is_available():
            return provider, model_id
    return None


def _build_messages(
    system: str | None, history: list[dict] | None, user_text: str
) -> list[Message]:
    messages: list[Message] = []
    if system:
        messages.append(Message("system", system))
    for pair in history or []:
        messages.append(Message("user", pair["q"]))
        messages.append(Message("assistant", pair["a"]))
    messages.append(Message("user", user_text))
    return messages


async def _chat_with_retry(
    provider: TextProvider, messages: list[Message], model_id: str,
    *, session=None, acc=None, locale: str = "ru", model_key: str | None = None,
) -> TextResult:
    """Call ``provider.chat`` with short backoff retries on transient errors
    (429 / 5xx), so a momentary rate-limit doesn't immediately surface as a
    "try later" message. Non-transient errors (bad key / no credits) re-raise on
    the first attempt; the last error re-raises once retries are exhausted, and
    the caller classifies it (sideline account / legacy fallback).

    FIX: AUDIT12-2 - accept session/acc/locale/model_key as keyword params so the
    retry loop can mark accounts exhausted when a 429/401/403 occurs. Without this
    fix, the router silently retries forever on every failed turn (money leak).
    """
    from core.i18n import t
    last_exc: Exception | None = None
    for delay in (0.0, *_RETRY_BACKOFFS):
        if delay:
            await asyncio.sleep(delay)
        try:
            return await provider.chat(messages, model_id)
        except Exception as exc:  # noqa: BLE001 — classify and try the next account
            last_exc = exc
            status = _status_code(exc)
            # FIX: AUDIT12-2 - mark the account exhausted/error when session+acc
            # are provided so the router moves on instead of retrying forever.
            # FIX: AUDIT13-L3 - only mark_exhausted here (once, then break). Do NOT call
            # mark_error for a transient 5xx inside the retry loop: that fired on every
            # attempt and inflated total_errors ~3x per sidelined account (the AUDIT-M11
            # comment's "1 per account" only held for the exhausted branch). A single
            # mark_error for an exhausted-retries 5xx is issued once, after the loop.
            if session is not None and acc is not None and status in _EXHAUSTED_STATUSES:
                try:
                    from core.services import ai_routing as _routing
                    await _routing.mark_exhausted(session, acc, error=_sanitize_exc(exc))
                except Exception as mark_err:  # noqa: BLE001
                    import structlog
                    structlog.get_logger().warning("ai_router.mark_failed", account=getattr(acc, "id", None), error=str(mark_err))
            # FIX: AUDIT-M11 - stop retrying the SAME account when an immediate retry
            # can't help: it was sidelined (429/401/402/403 → cooldown, so the caller
            # moves to the next account) or the status is permanently non-retryable.
            # Only a genuine transient 5xx blip retries the same account.
            if status in _EXHAUSTED_STATUSES or (status is not None and status not in _RETRY_STATUSES):
                break
            continue

    # FIX: AUDIT13-L3 - retries exhausted on a transient 5xx: record ONE error for the
    # account's health counter (not one per attempt). Exhausted statuses were already
    # marked (and broke) inside the loop, so skip them here.
    if session is not None and acc is not None and last_exc is not None:
        _final_status = _status_code(last_exc)
        if _final_status is not None and _final_status >= 500 and _final_status not in _EXHAUSTED_STATUSES:
            try:
                from core.services import ai_routing as _routing
                await _routing.mark_error(session, acc, _sanitize_exc(last_exc))
            except Exception as mark_err:  # noqa: BLE001
                import structlog
                structlog.get_logger().warning("ai_router.mark_failed", account=getattr(acc, "id", None), error=str(mark_err))

    # FIX: AUDIT12-2 - all retries exhausted; re-raise so the caller can decide
    # the user-facing message (rate_limit vs unavailable) instead of swallowing.
    if last_exc is not None:
        raise last_exc
    # FIX: AUDIT-13 - return ai.unavailable when no provider attempted
    return TextResult(text=t("ai.unavailable", locale), model=model_key or model_id, ok=False)


async def _chat_legacy(model_key: str, messages: list[Message], locale: str) -> TextResult:
    """Env-key routing used when no AIAccount rows exist (dev / before migration)."""
    from core.i18n import t

    provider, model_id = provider_for(model_key)
    if provider is None or not provider.is_available():
        fallback = _first_available()
        if fallback is None:
            return TextResult(text=t("ai.unavailable", locale), model=model_key, ok=False)
        provider, model_id = fallback

    try:
        # FIX: AUDIT12-2 - legacy path has no admin account to sideline
        return await _chat_with_retry(provider, messages, model_id, locale=locale, model_key=model_key)
    except Exception as exc:  # noqa: BLE001 — surface a user-friendly message
        # FIX: F26 - use _status_code so google-genai's .status is recognised too.
        status = _status_code(exc)
        if status == 429:
            return TextResult(text=t("ai.rate_limit", locale), model=model_key, ok=False)
        return TextResult(text=t("ai.unavailable", locale), model=model_key, ok=False)


async def chat(
    model_key: str,
    user_text: str,
    *,
    system: str | None = None,
    history: list[dict] | None = None,
    locale: str = "ru",
) -> TextResult:
    """Route a chat turn: admin-controlled account pool first (OmniRoute → fallback),
    then legacy env-key routing, with graceful localized fallback throughout."""
    from core.db import SessionFactory
    from core.services import ai_routing as routing

    messages = _build_messages(system, history, user_text)

    try:
        async with SessionFactory() as session:
            if await routing.has_accounts(session):
                result = await _chat_via_accounts(session, model_key, messages, locale)
                if result is not None:
                    return result
    except Exception as exc:  # noqa: BLE001 — FIX: L9 - log so DB routing failure is observable
        import structlog
        structlog.get_logger().warning("registry.db_routing_unavailable", error=str(exc))
        # fall back to legacy env-key routing below

    return await _chat_legacy(model_key, messages, locale)


async def _chat_via_accounts(
    session, model_key: str, messages: list[Message], locale: str
) -> TextResult | None:
    """FIX: AUDIT12-1 - implement the admin-account routing path. Iterates the
    ordered candidate pool, decrypts each account's api_key, builds an
    OpenAI-compatible provider, marks the account exhausted/error on failure,
    and returns the first successful result. Returns None when no candidate
    produced a successful turn (so the caller falls back to legacy routing)."""
    from core.i18n import t
    from core.services import ai_routing as routing
    from core.services.crypto import decrypt

    model = await routing.resolve_model(session, model_key)
    if model is None:
        return None
    accounts = await routing.candidate_accounts(session, model.modality, kind=model.account_kind)
    if not accounts:
        return None

    last_status: int | None = None
    for acc in accounts:
        try:
            prov = OpenAICompatibleText(
                decrypt(acc.api_key), base_url=acc.base_url, name=acc.kind,
            )
        except Exception:  # noqa: BLE001 - bad key/decrypt, skip this account
            continue
        if not prov.is_available():
            continue
        try:
            result = await _chat_with_retry(
                prov, messages, model.upstream_model,
                session=session, acc=acc, locale=locale, model_key=model_key,
            )
            await routing.mark_success(session, acc, latency_ms=None)
            await session.commit()
            return result
        except Exception as exc:  # noqa: BLE001 - already marked via _chat_with_retry
            last_status = _status_code(exc)
            continue

    # All accounts exhausted - signal caller to fall back to legacy env routing.
    if last_status == 429:
        return TextResult(text=t("ai.rate_limit", locale), model=model_key, ok=False)
    return None


async def _resolve_stream_provider(model_key: str) -> tuple[TextProvider, str]:
    """Pick a streaming-capable, available provider (admin account → legacy env).
    Raises ProviderUnavailable when none can stream — the caller then falls back to
    the non-streaming chat()."""
    from core.db import SessionFactory
    from core.services import ai_routing as routing

    # Prefer an admin-configured account (all OpenAI-compatible → support streaming).
    try:
        async with SessionFactory() as session:
            if await routing.has_accounts(session):
                model = await routing.resolve_model(session, model_key)
                if model is not None:
                    accounts = await routing.candidate_accounts(session, model.modality)
                    if accounts:
                        from core.services.crypto import decrypt
                        acc = accounts[0]
                        prov = OpenAICompatibleText(
                            decrypt(acc.api_key), base_url=acc.base_url, name=acc.kind
                        )
                        if hasattr(prov, "chat_stream") and prov.is_available():
                            return prov, model.upstream_model
    except Exception:  # noqa: BLE001 — DB routing unavailable → legacy path
        pass

    provider, model_id = provider_for(model_key)
    if provider is None or not provider.is_available():
        fb = _first_available()
        if fb is None:
            raise ProviderUnavailable(model_key)
        provider, model_id = fb
    if not hasattr(provider, "chat_stream"):
        raise ProviderUnavailable(model_key)
    return provider, model_id


async def chat_stream(
    model_key: str,
    user_text: str,
    *,
    system: str | None = None,
    history: list[dict] | None = None,
    locale: str = "ru",
) -> AsyncIterator[str]:
    """Stream a chat turn as text deltas (ТЗ §3). Resolution errors surface as
    ProviderUnavailable on the first iteration (nothing yielded yet), so the caller
    can fall back to the buffered chat() without having shown a partial reply."""
    provider, model_id = await _resolve_stream_provider(model_key)
    messages = _build_messages(system, history, user_text)
    async for delta in provider.chat_stream(messages, model_id):
        yield delta
