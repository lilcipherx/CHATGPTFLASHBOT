"""Lightweight i18n facade.

RU is the canonical locale (verbatim from the report); other locales fall back
to RU for any missing key. Translations live as plain dicts per locale which is
robust for the long multi-line verbatim strings; migrating to Fluent .ftl later
only touches this module.
"""
from __future__ import annotations

import importlib

from core.constants import SUPPORTED_LOCALES

_CACHE: dict[str, dict[str, str]] = {}


def _load(locale: str) -> dict[str, str]:
    if locale not in _CACHE:
        try:
            mod = importlib.import_module(f"core.i18n.locales.{locale}")
            _CACHE[locale] = getattr(mod, "MESSAGES", {})
        except Exception as exc:  # FIX: AUDIT-143 - broaden to catch SyntaxError, ImportError, etc.
            import structlog
            structlog.get_logger().warning("i18n.load_failed", locale=locale, error=str(exc))
            _CACHE[locale] = {}
    return _CACHE[locale]


def static_message(key: str, locale: str = "ru") -> str | None:
    """The static (non-overridden) message for (locale, key) with the usual RU
    fallback, or None when the key is unknown. Used by the admin localization editor
    to show what an override falls back to."""
    msg = _load(locale).get(key)
    if msg is None and locale != "ru":
        msg = _load("ru").get(key)
    return msg


def known_keys() -> list[str]:
    """Every message key across all locales (union), sorted — the editable set the
    admin localization UI lists."""
    keys: set[str] = set()
    for locale in SUPPORTED_LOCALES:
        keys.update(_load(locale).keys())
    return sorted(keys)


def locale_keys(locale: str) -> set[str]:
    """Keys with an OWN translation in `locale` (i.e. not served via the RU
    fallback). Used by the admin editor's per-language coverage stats."""
    return set(_load(locale).keys())


def _override(locale: str, key: str) -> str | None:
    """Admin text override for (locale, key) from the live overrides snapshot, or
    None. Imported lazily to avoid a core.services <-> core.i18n import cycle, and
    wrapped so the translator never breaks if the overrides layer is unavailable."""
    try:
        from core.services import i18n_overrides

        return i18n_overrides.lookup(locale, key)
    except Exception as exc:  # noqa: BLE001 — FIX: F36 - log so a broken overrides
        # layer silently degrading every user to static text is observable.
        # Behaviour unchanged: overrides are best-effort, fall back to static.
        import structlog
        structlog.get_logger().warning(
            "i18n.override_failed", locale=locale, key=key, error=str(exc)
        )
        return None


def t(key: str, locale: str = "ru", **kwargs) -> str:
    locale = locale if locale in SUPPORTED_LOCALES else "ru"
    # Admin overrides win over the static dict (and over the RU fallback).
    msg = _override(locale, key)
    if msg is None:
        msg = _load(locale).get(key)
    if msg is None and locale != "ru":
        msg = _override("ru", key)
    if msg is None and locale != "ru":
        msg = _load("ru").get(key)
    if msg is None:
        return key
    if not kwargs:
        return msg
    try:
        return msg.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        # A bad admin override (an unknown/extra {placeholder} or a stray brace)
        # must NEVER crash the bot at render time for every user of this locale.
        # Fall back to the static message for this key; if that also can't format,
        # return it raw rather than propagating.
        static = _load(locale).get(key) or _load("ru").get(key) or key
        try:
            return static.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return static


def all_labels(key: str) -> set[str]:
    """Every localized value of `key` across all locales (+ RU fallback).

    Used by reply-keyboard handlers so a button matches regardless of the user's
    interface language."""
    labels: set[str] = set()
    for locale in SUPPORTED_LOCALES:
        val = _load(locale).get(key)
        if val:
            labels.add(val)
    ru = _load("ru").get(key)
    if ru:
        labels.add(ru)
    return labels


class Translator:
    """Bound to a single user's locale — passed into handlers by middleware."""

    def __init__(self, locale: str = "ru"):
        self.locale = locale

    def __call__(self, key: str, **kwargs) -> str:
        return t(key, self.locale, **kwargs)
