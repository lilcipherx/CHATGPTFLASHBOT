"""Admin: contests / giveaways (ТЗ §7).

An admin creates a giveaway, watches the entrant count, then draws random
winners (best-effort notifying each via the bot). Every mutation is audited."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import require_role
from core.bot_client import get_bot
from core.db import get_session
from core.models import AdminAuditLog, AdminUser
from core.models.contest import ContestEntry
from core.services import contests

router = APIRouter(prefix="/contests", tags=["admin-contests"])
log = structlog.get_logger()


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _card(c: contests.Contest, entrants: int) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "description": c.description,
        "status": c.status,
        "winners_count": c.winners_count,
        "prize_type": c.prize_type,
        "prize_amount": c.prize_amount,
        "entrants": entrants,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "drawn_at": c.drawn_at.isoformat() if c.drawn_at else None,
    }


@router.get("")
async def list_contests(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """All contests with their entrant counts, newest first."""
    rows = await contests.list_all(session)
    # FIX: AUDIT12-M3 - single GROUP BY query instead of N+1 per-contest COUNT(*).
    # Was: for c in rows: await contests.entrants_count(session, c.id) — issued one
    # extra SELECT per contest, so listing 100 contests ran 101 queries.
    from sqlalchemy import func

    counts_map: dict[int, int] = {}
    if rows:
        counts_map = dict((await session.execute(
            select(ContestEntry.contest_id, func.count())
            .where(ContestEntry.contest_id.in_([c.id for c in rows]))
            .group_by(ContestEntry.contest_id)
        )).all())
    return [_card(c, counts_map.get(c.id, 0)) for c in rows]


class CreateContest(BaseModel):
    # FIX: AUDIT12-26 - bounded strings + numeric ranges
    title: str = Field(..., max_length=200)
    description: str | None = Field(None, max_length=1000)
    winners_count: int = Field(1, ge=1, le=1000)
    prize_type: str = Field("credits", max_length=20)   # credits | image | video | music
    prize_amount: int = Field(0, ge=0, le=10_000_000)         # 0 = no auto-prize (notify-only)


@router.post("")
async def create_contest(
    req: CreateContest,
    request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    c = await contests.create(
        session, req.title, req.description, req.winners_count,
        prize_type=req.prize_type, prize_amount=req.prize_amount,
    )
    await audit(
        session, admin_id=admin.id, action="contest.create",
        target_type="contest", target_id=str(c.id),
        after={"title": c.title, "winners_count": c.winners_count,
               "prize_type": c.prize_type, "prize_amount": c.prize_amount}, ip=_ip(request),
    )
    return _card(c, 0)


class UpdateContest(BaseModel):
    # FIX: AUDIT12-26 - mirror CreateContest bounds
    title: str = Field(..., max_length=200)
    description: str | None = Field(None, max_length=1000)
    winners_count: int = Field(1, ge=1, le=1000)
    prize_type: str = Field("credits", max_length=20)
    prize_amount: int = Field(0, ge=0, le=10_000_000)


@router.put("/{contest_id}")
async def update_contest(
    contest_id: int, req: UpdateContest, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Edit a contest's title / description / winners_count / prize. Only allowed
    BEFORE the draw — changing the winners or prize after a draw would be misleading."""
    c = await session.get(contests.Contest, contest_id)
    if c is None:
        raise HTTPException(status_code=404, detail="not found")
    # FIX: R15 - lock the row so two rapid "Save" clicks (or a save racing a draw)
    # can't overwrite each other. The drawn-status check is then re-read under the
    # lock so we never edit a row that was just drawn.
    await session.refresh(c, with_for_update=True)
    if c.status == "drawn":
        raise HTTPException(status_code=400, detail="cannot edit a drawn contest")
    if not req.title.strip():
        raise HTTPException(status_code=400, detail="title required")
    ptype, amount = contests._clean_prize(req.prize_type, req.prize_amount)
    c.title = req.title.strip()
    c.description = (req.description or "").strip() or None
    c.winners_count = max(1, req.winners_count)
    c.prize_type = ptype
    c.prize_amount = amount
    await session.commit()
    await session.refresh(c)
    await audit(session, admin_id=admin.id, action="contest.update", target_type="contest",
                target_id=str(contest_id),
                after={"title": c.title, "winners_count": c.winners_count,
                       "prize_type": c.prize_type, "prize_amount": c.prize_amount},
                ip=_ip(request))
    n = await contests.entrants_count(session, c.id)
    return _card(c, n)


@router.get("/{contest_id}/entrants")
async def contest_entrants(
    contest_id: int, limit: int = 500,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """User ids that entered this contest, newest first (bounded)."""
    limit = max(1, min(limit, 2000))
    rows = (await session.execute(
        select(ContestEntry.user_id, ContestEntry.created_at)
        .where(ContestEntry.contest_id == contest_id)
        .order_by(ContestEntry.created_at.desc())
        .limit(limit)
    )).all()
    return {
        "entrants": [
            {"user_id": uid, "entered_at": ts.isoformat() if ts else None}
            for uid, ts in rows
        ],
    }


@router.get("/{contest_id}/winners")
async def contest_winners(
    contest_id: int,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Winners of a drawn contest, recovered from the most recent draw audit entry
    (winners aren't stored on the contest itself). Empty when never drawn."""
    row = await session.scalar(
        select(AdminAuditLog)
        .where(AdminAuditLog.action == "contest.draw", AdminAuditLog.target_id == str(contest_id))
        .order_by(AdminAuditLog.created_at.desc())
        .limit(1)
    )
    winners = (row.after or {}).get("winners", []) if row else []
    return {"winners": winners, "drawn_at": row.created_at.isoformat() if row else None}


@router.post("/{contest_id}/draw")
async def draw_contest(
    contest_id: int,
    request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Draw random winners (auto-granting any prize), audit, and best-effort notify
    each winner in their own language, naming the prize they won."""
    # Capture the prize BEFORE the draw — draw() expires the contest row, and the
    # winners need to be told what they won.
    c = await session.get(contests.Contest, contest_id)
    prize_type = c.prize_type if c else "credits"
    prize_amount = c.prize_amount if c else 0

    try:
        # FIX: AUDIT12-16 - draw with commit=False so the audit row lands in the
        # SAME transaction as the prize grants (was: draw() committed internally,
        # then audit() ran in a separate tx → DB failure between them lost audit).
        winners = await contests.draw(session, contest_id, commit=False)
    except contests.ContestError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    await audit(
        session, admin_id=admin.id, action="contest.draw",
        target_type="contest", target_id=str(contest_id),
        after={"winners": winners, "prize_type": prize_type, "prize_amount": prize_amount},
        ip=_ip(request), commit=False,
    )
    await session.commit()

    bot = get_bot()
    for uid in winners:
        try:
            await bot.send_message(uid, await _win_message(session, uid, prize_type, prize_amount))
        except Exception:  # noqa: BLE001
            log.warning("contest.notify_failed", contest_id=contest_id, user_id=uid)

    return {"ok": True, "id": contest_id, "winners": winners}


# Pack-prize unit emoji, so the win message names the reward without needing a
# localized pack noun in every language.
_PRIZE_EMOJI = {"image": "🖼", "video": "🎬", "music": "🎵"}


async def _win_message(
    session: AsyncSession, user_id: int, prize_type: str, prize_amount: int
) -> str:
    """Localized 'you won' message. Names the auto-prize (✨ amount or pack units)
    when there is one; falls back to a plain congrats when the prize is notify-only."""
    from core.i18n import t
    from core.services.users import user_locale

    locale = await user_locale(session, user_id)
    if prize_amount > 0 and prize_type == "credits":
        return t("contest.won_credits", locale, amount=prize_amount)
    if prize_amount > 0 and prize_type in _PRIZE_EMOJI:
        return t("contest.won_pack", locale, amount=prize_amount, unit=_PRIZE_EMOJI[prize_type])
    return t("contest.won", locale)


@router.post("/{contest_id}/close")
async def close_contest(
    contest_id: int,
    request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        c = await contests.close(session, contest_id)
    except contests.ContestError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await audit(
        session, admin_id=admin.id, action="contest.close",
        target_type="contest", target_id=str(contest_id),
        after={"status": c.status}, ip=_ip(request),
    )
    return {"ok": True, "id": c.id, "status": c.status}
