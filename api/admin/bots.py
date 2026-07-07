"""Admin: multi-bot / white-label registry (ТЗ §0).

CRUD over BotInstance rows. Bot tokens are secrets — stored encrypted and NEVER
returned (only a masked tail). Mutations require superadmin; all are audited.
Adding/removing a bot takes effect on the next launcher start (the polling
launcher reads active instances at boot)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core.db import get_session
from core.models import AdminUser, GenerationJob, User
from core.services import bots as bots_svc
from core.services.crypto import decrypt

router = APIRouter(prefix="/bots", tags=["admin-bots"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _mask(token_enc: str) -> str:
    tok = decrypt(token_enc)
    return f"…{tok[-6:]}" if tok and len(tok) > 6 else "****"


def _dict(b) -> dict:
    return {
        "id": b.id,
        "title": b.title,
        "token_masked": _mask(b.token),
        "tg_bot_id": b.tg_bot_id,
        "username": b.username,
        "active": b.active,
        "is_default": b.is_default,
        # Timestamps already live on the model (TimestampMixin) — no migration.
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


@router.get("")
async def list_bots(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return [_dict(b) for b in await bots_svc.list_bots(session)]


@router.get("/stats")
async def bots_stats(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Real per-bot engagement, computed from tenant attribution (``User.bot_id``):
    how many users arrived through each bot, how many generation jobs they ran, and
    the most recent signup / request per bot. Users with a NULL bot_id (the primary /
    legacy single-bot bucket) are returned under the "legacy" key. No migration — pure
    aggregates over existing columns/indexes."""

    def bucket(bot_id: int | None) -> str:
        return "legacy" if bot_id is None else str(bot_id)

    stats: dict[str, dict] = {}

    users_rows = await session.execute(
        select(User.bot_id, func.count(), func.max(User.created_at)).group_by(User.bot_id)
    )
    for bot_id, cnt, last in users_rows:
        d = stats.setdefault(bucket(bot_id), {})
        d["users"] = int(cnt or 0)
        d["last_user_at"] = last.isoformat() if last else None

    req_rows = await session.execute(
        select(User.bot_id, func.count(GenerationJob.job_id), func.max(GenerationJob.created_at))
        .select_from(GenerationJob)
        .join(User, GenerationJob.user_id == User.user_id)
        .group_by(User.bot_id)
    )
    for bot_id, cnt, last in req_rows:
        d = stats.setdefault(bucket(bot_id), {})
        d["requests"] = int(cnt or 0)
        d["last_request_at"] = last.isoformat() if last else None

    for d in stats.values():
        d.setdefault("users", 0)
        d.setdefault("requests", 0)
        d.setdefault("last_user_at", None)
        d.setdefault("last_request_at", None)

    totals = {
        "users": sum(d["users"] for d in stats.values()),
        "requests": sum(d["requests"] for d in stats.values()),
    }
    return {"stats": stats, "totals": totals}


class BotCreate(BaseModel):
    title: str
    token: str
    is_default: bool = False


class TokenCheck(BaseModel):
    token: str


@router.post("/check-token")
async def check_token(
    req: TokenCheck,
    admin: AdminUser = Depends(require_role("admin")),
) -> dict:
    """Validate a raw token via Telegram getMe before saving it (create form /
    rotation field). Read-only: shows @username, Bot ID and whether it's alive,
    without persisting — identity is still recorded by the launcher on first run."""
    return await bots_svc.verify_token(req.token)


@router.post("/{bot_id}/check")
async def check_bot(
    bot_id: int,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Validate an EXISTING bot's stored token via getMe (decrypted server-side)."""
    b = await bots_svc.get_bot(session, bot_id)
    if b is None:
        raise HTTPException(status_code=404, detail="not found")
    from core.services.crypto import decrypt
    return await bots_svc.verify_token(decrypt(b.token))


@router.post("")
async def create_bot(
    req: BotCreate, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not req.token.strip() or ":" not in req.token:
        raise HTTPException(status_code=400, detail="invalid bot token")
    if await bots_svc.token_in_use(session, req.token):
        raise HTTPException(status_code=400, detail="этот токен уже зарегистрирован у другого бота")
    b = await bots_svc.create_bot(
        session, title=req.title.strip() or "Bot", token=req.token.strip(),
        is_default=req.is_default,
    )
    await audit(session, admin_id=admin.id, action="bot.create", target_type="bot",
                target_id=str(b.id), after={"title": b.title}, ip=_ip(request))
    return _dict(b)


class BotUpdate(BaseModel):
    title: str | None = None
    token: str | None = None        # empty/None = keep existing
    active: bool | None = None
    is_default: bool | None = None


@router.put("/{bot_id}")
async def update_bot(
    bot_id: int, req: BotUpdate, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if req.token and ":" not in req.token:
        raise HTTPException(status_code=400, detail="invalid bot token")
    target = await bots_svc.get_bot(session, bot_id)
    if target is None:
        raise HTTPException(status_code=404, detail="not found")
    # The default bot owns legacy users (bot_id = NULL) and is the routing fallback —
    # don't let it be disabled out from under them; reassign default first.
    if req.active is False and target.is_default:
        raise HTTPException(
            status_code=400,
            detail="нельзя отключить бота по умолчанию — сначала назначьте другого",
        )
    if req.token and await bots_svc.token_in_use(session, req.token, exclude_id=bot_id):
        raise HTTPException(status_code=400, detail="этот токен уже зарегистрирован у другого бота")
    b = await bots_svc.update_bot(
        session, bot_id, title=req.title, token=req.token,
        active=req.active, is_default=req.is_default,
    )
    if b is None:
        raise HTTPException(status_code=404, detail="not found")
    await audit(session, admin_id=admin.id, action="bot.update", target_type="bot",
                target_id=str(bot_id), after={"active": b.active}, ip=_ip(request))
    return _dict(b)


@router.delete("/{bot_id}")
async def delete_bot(
    bot_id: int, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    target = await bots_svc.get_bot(session, bot_id)
    if target is None:
        raise HTTPException(status_code=404, detail="not found")
    if target.is_default:
        raise HTTPException(
            status_code=400,
            detail="нельзя удалить бота по умолчанию — сначала назначьте другого",
        )
    ok = await bots_svc.delete_bot(session, bot_id)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    await audit(session, admin_id=admin.id, action="bot.delete", target_type="bot",
                target_id=str(bot_id), ip=_ip(request))
    return {"ok": True}
