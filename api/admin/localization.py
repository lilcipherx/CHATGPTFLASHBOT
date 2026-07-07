"""Admin: live localization editor — override any bot text string per-locale from
the panel, applied live without a redeploy (ТЗ §8 «Редактор локализации»).

Read = admin; writes are audited. Backed by core.services.i18n_overrides, which
stores overrides in the `pricing` KV table and refreshes the bot's in-memory
translator snapshot within seconds.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core import i18n
from core.constants import LANGUAGES, SUPPORTED_LOCALES
from core.db import get_session
from core.models import AdminAuditLog, AdminUser
from core.services import i18n_overrides, i18n_translate

router = APIRouter(prefix="/localization", tags=["admin-localization"])

# Locales written right-to-left (real attribute, drives the editor's RTL badge +
# preview direction). Only `ar` is in the catalogue today; the set is future-proof.
_RTL = {"ar", "he", "fa", "ur"}


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _placeholders(s: str) -> set[str]:
    """Named {placeholders} in a format string. Raises ValueError on malformed
    braces (a stray '{' / '}'), which we surface as a 400 below."""
    import string

    return {fname for _, fname, _, _ in string.Formatter().parse(s) if fname}


def _validate_override_text(locale: str, key: str, text: str) -> None:
    """An override is rendered via str.format(**kwargs) at runtime, so a placeholder
    the caller doesn't supply (or a malformed brace) would raise and break the
    message for every user of this locale. Reject up front: the override may only
    use placeholders the static default already uses. (The translator also guards
    this at render time, but a 400 tells the admin immediately instead of silently
    falling back.)"""
    default = i18n.static_message(key, locale) or i18n.static_message(key, "ru") or ""
    try:
        allowed = _placeholders(default)
        used = _placeholders(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"malformed placeholder: {exc}") from exc
    extra = used - allowed
    if extra:
        raise HTTPException(
            status_code=400,
            detail=f"unknown placeholders {sorted(extra)}; allowed: {sorted(allowed)}",
        )


@router.get("")
async def get_localization(
    locale: str = "ru",
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Merged map for a locale: every known key with its static default + any
    override (so the UI can show both and let the admin edit/revert)."""
    if locale not in SUPPORTED_LOCALES:
        raise HTTPException(status_code=400, detail="unsupported locale")
    overrides = (await i18n_overrides.get_overrides(session)).get(locale, {})
    rows = []
    for key in i18n.known_keys():
        default = i18n.static_message(key, locale) or ""
        rows.append({
            "key": key,
            "default": default,
            "override": overrides.get(key),  # None = not overridden
        })
    return {
        "locale": locale,
        "locales": [{"code": code, "label": label} for code, label in LANGUAGES],
        "items": rows,
    }


@router.get("/stats")
async def localization_stats(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Per-language coverage for the Language Manager: how many keys each locale
    translates natively (vs. falling back to RU), how many admin overrides it has,
    and a completeness percent. Pure in-memory over the i18n dicts + override map —
    no migration."""
    all_keys = i18n.known_keys()
    total = len(all_keys)
    overrides = await i18n_overrides.get_overrides(session)
    langs = []
    for code, label in LANGUAGES:
        own = i18n.locale_keys(code)
        translated = sum(1 for k in all_keys if k in own)
        langs.append({
            "code": code,
            "label": label,
            "rtl": code in _RTL,
            "is_default": code == "ru",
            "translated": translated,
            "missing": total - translated,
            "overrides": len(overrides.get(code, {})),
            "percent": round(translated / total * 100) if total else 0,
        })
    return {"total": total, "languages": langs}


@router.get("/history")
async def localization_history(
    locale: str,
    key: str,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Real change history for one (locale, key) from the audit log — author, time,
    the value that was set (for set actions) — newest first. Powers the editor's diff
    viewer and rollback (re-applying a previous value via PUT)."""
    if locale not in SUPPORTED_LOCALES:
        raise HTTPException(status_code=400, detail="unsupported locale")
    target = f"{locale}:{key}"
    rows = (await session.scalars(
        select(AdminAuditLog)
        .where(
            AdminAuditLog.target_type == "text_override",
            AdminAuditLog.target_id == target,
        )
        .order_by(AdminAuditLog.created_at.desc())
        .limit(50)
    )).all()
    out = []
    for r in rows:
        text = (r.after or {}).get("text") if r.action == "localization.set" else None
        out.append({
            "id": r.id,
            "admin_id": r.admin_id,
            "action": r.action,
            "created_at": r.created_at.isoformat(),
            "text": text,
        })
    return out


class OverridePut(BaseModel):
    locale: str
    key: str
    text: str


@router.put("")
async def put_override(
    req: OverridePut,
    request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Set an override for (locale, key). Applies live."""
    if req.locale not in SUPPORTED_LOCALES:
        raise HTTPException(status_code=400, detail="unsupported locale")
    _validate_override_text(req.locale, req.key, req.text)
    try:
        await i18n_overrides.set_override(session, req.locale, req.key, req.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await audit(
        session, admin_id=admin.id, action="localization.set",
        target_type="text_override", target_id=f"{req.locale}:{req.key}",
        after={"locale": req.locale, "key": req.key, "text": req.text}, ip=_ip(request),
    )
    return {"ok": True}


class TranslateReq(BaseModel):
    locale: str
    key: str | None = None      # source = this key's RU default …
    text: str | None = None     # … or an explicit source string (takes precedence)


@router.post("/translate")
async def translate_text(
    req: TranslateReq,
    admin: AdminUser = Depends(require_role("admin")),
) -> dict:
    """Machine-translate the RU source of (key) — or an explicit `text` — into
    `locale` via the configured OpenAI key, preserving placeholders. Returns a
    SUGGESTION only ({text}); the admin reviews and saves it via PUT. Not audited
    because nothing is persisted here."""
    if req.locale not in SUPPORTED_LOCALES:
        raise HTTPException(status_code=400, detail="unsupported locale")
    source = req.text if req.text is not None else (
        i18n.static_message(req.key, "ru") if req.key else None
    )
    try:
        out = await i18n_translate.translate(source or "", req.locale)
    except i18n_translate.TranslateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"text": out}


@router.delete("")
async def delete_override(
    locale: str,
    key: str,
    request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Clear an override (revert to the static message). Applies live."""
    if locale not in SUPPORTED_LOCALES:
        raise HTTPException(status_code=400, detail="unsupported locale")
    existed = await i18n_overrides.clear_override(session, locale, key)
    await audit(
        session, admin_id=admin.id, action="localization.clear",
        target_type="text_override", target_id=f"{locale}:{key}",
        before={"locale": locale, "key": key}, ip=_ip(request),
    )
    return {"ok": True, "existed": existed}
