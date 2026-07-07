"""Admin-only machine translation for the localization editor (ТЗ §8).

Translates a Russian source string into a target locale through the platform's AI
router (``core.ai_router.registry.chat``) — i.e. the SAME account/provider routing,
fallback and cooldown logic the bot's chat uses. This means translation needs no
separate key configuration: it works whenever the bot's text chat works, and shares
its provider failover. The model is instructed to keep every ``{placeholder}``
verbatim. This only RETURNS a suggestion — the admin reviews it in the editor and
decides whether to save it as an override. Nothing is persisted here.
"""
from __future__ import annotations

import string

from core.config import settings
from core.constants import SUPPORTED_LOCALES

# English language names for the prompt (clearer for the model than locale codes).
_TARGET_NAME = {
    "en": "English",
    "ru": "Russian",
    "uz": "Uzbek",
    "es": "Spanish",
    "fr": "French",
    "ar": "Arabic",
    "pt": "Brazilian Portuguese",
    "zh": "Simplified Chinese",
}


class TranslateError(Exception):
    """Raised for any translation failure (bad locale, empty source, routing down)."""


def _placeholders(s: str) -> set[str]:
    return {fname for _, fname, _, _ in string.Formatter().parse(s) if fname}


async def translate(source: str, target_locale: str) -> str:
    """Translate `source` (Russian) into `target_locale` via the AI router. Raises
    TranslateError on any problem. Placeholders are preserved by instruction; we never
    raise on a dropped one — the editor's QA panel flags it for the admin."""
    if target_locale not in SUPPORTED_LOCALES:
        raise TranslateError("unsupported locale")
    src = (source or "").strip()
    if not src:
        raise TranslateError("нет исходного текста для перевода")
    if target_locale == "ru":
        # RU is the canonical source — nothing to translate into.
        return src

    target = _TARGET_NAME.get(target_locale, target_locale)
    placeholders = _placeholders(src)
    ph_note = (
        " Keep these placeholders EXACTLY as written, never translate or alter them: "
        + ", ".join("{" + p + "}" for p in sorted(placeholders))
        if placeholders else ""
    )
    system = (
        "You are a professional UI localizer for a Telegram bot. Translate the user's "
        f"message from Russian into {target}. Preserve the meaning, tone and ALL "
        "formatting — emoji, line breaks, and any Markdown/HTML tags. Output ONLY the "
        "translated string, with no quotes, notes or explanations." + ph_note
    )

    # Lazy import to avoid pulling the router (and its heavy deps) at module import.
    from core.ai_router import registry

    try:
        result = await registry.chat(
            settings.localization_translate_model_key, src,
            system=system, locale=target_locale,
        )
    except Exception as exc:  # noqa: BLE001 — surface any routing error to the admin
        raise TranslateError(str(exc)[:200]) from exc

    out = (result.text or "").strip()
    # On failure the router returns a localized "AI busy / unavailable" placeholder with
    # ok=False — that is NOT a translation, so reject it instead of saving it as one.
    if not result.ok or not out:
        raise TranslateError(
            "маршрутизация ИИ недоступна — проверьте аккаунты/ключи (стр. AI-роутинг)"
        )
    return out
