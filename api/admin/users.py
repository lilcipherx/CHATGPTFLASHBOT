"""Admin: user search + management actions (§11A.2)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import like_contains, require_role
from core.constants import SUBSCRIPTION_PRICES
from core.db import get_session
from core.models import AdminUser, GenerationJob, PackBalance, Transaction, User
from core.services import credits, packs
from core.services.admin_auth import ROLE_RANK  # FIX: AUDIT13-H2 - rank-based credit cap
from core.services.context import clear_context
from core.services.notifications import notify_user

router = APIRouter(prefix="/users", tags=["admin-users"])

# support can compensate up to this many credits per action (§11A.1)
SUPPORT_CREDIT_LIMIT = 50


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


# Column the result set is ordered by → SQL expression. Keeps sorting to a known
# allow-list (no arbitrary user-supplied ORDER BY).
_SORTS = {
    "created_desc": User.created_at.desc(),
    "created_asc": User.created_at.asc(),
    "credits_desc": User.credits.desc(),
    "credits_asc": User.credits.asc(),
}


@router.get("")
async def search_users(
    q: str = "",
    premium: bool | None = None,
    banned: bool | None = None,
    country: str = "",
    language: str = "",
    has_phone: bool | None = None,
    sort: str = "created_desc",
    limit: int = 50,
    offset: int = 0,
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Bounded pagination so the admin can page past the first screen without ever
    # asking the DB for an unbounded result set.
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    if sort not in _SORTS:
        sort = "created_desc"

    # Build the filter predicates once, then apply them to BOTH the count and the
    # page query so `total` reflects the same filtered set as `items`.
    conds = []
    if q:
        like = like_contains(q)
        qconds = [User.username.ilike(like, escape="\\"), User.phone.ilike(like, escape="\\")]
        if q.isdigit():
            qconds.append(User.user_id == int(q))
        conds.append(or_(*qconds))
    if premium is not None:
        # is_premium is a computed property; replicate its rule in SQL. Written
        # NULL-safely so every row lands in exactly one bucket (a row with a tier
        # but no expiry must not vanish from both filters).
        now = datetime.now(UTC)
        if premium:
            conds.extend([
                User.sub_tier.isnot(None),
                User.sub_expires.isnot(None),
                User.sub_expires > now,
            ])
        else:
            conds.append(
                or_(User.sub_tier.is_(None), User.sub_expires.is_(None),
                    User.sub_expires <= now)
            )
    if banned is not None:
        conds.append(User.is_banned.is_(banned))
    if country:
        conds.append(User.country == country.upper())
    if language:
        conds.append(User.language_code == language.lower())
    if has_phone is not None:
        conds.append(User.phone.isnot(None) if has_phone else User.phone.is_(None))

    total = await session.scalar(
        select(func.count()).select_from(User).where(*conds)
    ) or 0
    stmt = (
        select(User).where(*conds)
        .order_by(_SORTS[sort]).limit(limit).offset(offset)
    )
    rows = (await session.scalars(stmt)).all()
    items = [
        {"user_id": u.user_id, "username": u.username, "sub_tier": u.sub_tier,
         "is_premium": u.is_premium, "is_banned": u.is_banned,
         "phone": u.phone, "country": u.country,
         "credits": u.credits,
         "created_at": u.created_at.isoformat() if u.created_at else None}
        for u in rows
    ]
    return {"items": items, "total": int(total), "limit": limit, "offset": offset, "sort": sort}


@router.get("/countries")
async def list_user_countries(
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Distinct user countries with counts, most-populous first — powers the country
    filter dropdown so the admin picks from real data instead of guessing ISO codes.
    Declared before /{user_id} so the literal path wins over the int converter."""
    rows = (await session.execute(
        select(User.country, func.count())
        .where(User.country.isnot(None), User.country != "")
        .group_by(User.country).order_by(func.count().desc())
    )).all()
    return [{"code": c, "count": int(n)} for c, n in rows]


@router.get("/languages")
async def list_user_languages(
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Distinct user languages with counts, most-common first. Unlike country (set
    only when a phone is shared), language_code is captured for EVERY user, so this is
    the reliable audience-segment signal."""
    rows = (await session.execute(
        select(User.language_code, func.count())
        .where(User.language_code.isnot(None), User.language_code != "")
        .group_by(User.language_code).order_by(func.count().desc())
    )).all()
    return [{"code": c, "count": int(n)} for c, n in rows]


@router.get("/{user_id}")
async def user_card(
    user_id: int,
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    u = await session.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="not found")
    bal = await session.get(PackBalance, user_id)
    txs = (await session.scalars(
        select(Transaction).where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc()).limit(20)
    )).all()
    jobs = (await session.scalars(
        select(GenerationJob).where(GenerationJob.user_id == user_id)
        .order_by(GenerationJob.created_at.desc()).limit(20)
    )).all()
    # lifetime credits spent across all generations
    credits_used = (await session.scalar(
        select(func.coalesce(func.sum(GenerationJob.cost_credits), 0))
        .where(GenerationJob.user_id == user_id)
    )) or 0
    # premium purchase history (paid subscription transactions)
    premium_txs = (await session.scalars(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.status == "paid",
            Transaction.product.in_(("premium", "premium_x2")),
        ).order_by(Transaction.created_at.desc())
    )).all()
    premium_purchases = [
        {"product": t.product, "months": t.duration_months, "amount": t.amount,
         "gateway": t.gateway, "at": (t.paid_at or t.created_at).isoformat()}
        for t in premium_txs
    ]
    referrals_count = (await session.scalar(
        select(func.count()).select_from(User).where(User.referred_by == user_id)
    )) or 0
    return {
        "user_id": u.user_id, "username": u.username, "language_code": u.language_code,
        "phone": u.phone, "country": u.country,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "sub_tier": u.sub_tier, "is_premium": u.is_premium,
        "sub_expires": u.sub_expires.isoformat() if u.sub_expires else None,
        "is_banned": u.is_banned, "credits": u.credits, "credits_used": int(credits_used),
        "referred_by": u.referred_by, "referrals_count": referrals_count,
        "premium_purchase_count": len(premium_purchases),
        "premium_purchases": premium_purchases,
        "balances": {
            "image": bal.image_credits if bal else 0,
            "video": bal.video_credits if bal else 0,
            "music": bal.music_credits if bal else 0,
        },
        "transactions": [
            {"product": t.product, "amount": t.amount, "gateway": t.gateway,
             "status": t.status, "created_at": t.created_at.isoformat()} for t in txs
        ],
        "jobs": [
            {"service": j.service, "status": j.status,
             "created_at": j.created_at.isoformat()} for j in jobs
        ],
    }


class BanRequest(BaseModel):
    banned: bool


@router.post("/{user_id}/ban")
async def set_ban(
    user_id: int, req: BanRequest, request: Request,
    admin: AdminUser = Depends(require_role("moderator", "admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    u = await session.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="not found")
    before = {"is_banned": u.is_banned}
    u.is_banned = req.banned
    locale = u.language_code
    # FIX: AUDIT-4 - audit FIRST (in same tx as mutation), notify_user AFTER (best-effort)
    await audit(session, admin_id=admin.id, action="user.ban", target_type="user",
                target_id=str(user_id), before=before, after={"is_banned": req.banned},
                ip=_client_ip(request), commit=False)
    await session.commit()
    try:
        await notify_user(user_id, "notify.banned" if req.banned else "notify.unbanned", locale)
    except Exception:
        pass
    return {"ok": True, "is_banned": u.is_banned}


class CreditsRequest(BaseModel):
    pack: str = Field(..., max_length=16)          # image | video | music | credits
    # FIX: AUDIT13-M8 - bound the grant/deduct amount. Was an unbounded int, so a typo
    # or rogue admin could mint up to 2^63 credits in one call.
    amount: int = Field(..., ge=-1_000_000, le=1_000_000)  # may be negative to deduct


@router.post("/{user_id}/credits")
async def grant_credits(
    user_id: int, req: CreditsRequest, request: Request,
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if req.pack not in ("image", "video", "music", "credits"):
        raise HTTPException(status_code=400, detail="bad pack")
    # FIX: AUDIT13-H2 - gate the cap on RANK, not the literal "support". The endpoint
    # is require_role("support"), so a moderator (rank 2) also reaches it; the old
    # `admin.role == "support"` check skipped the cap for moderators (neither "support"
    # nor admin+), letting a moderator mint UNLIMITED credits. Anyone below admin is capped.
    if ROLE_RANK.get(admin.role, 0) < ROLE_RANK["admin"] and abs(req.amount) > SUPPORT_CREDIT_LIMIT:
        raise HTTPException(status_code=403, detail="exceeds support limit")
    # Verify the user exists BEFORE any mutation — for ALL packs, not just credits.
    # A pack grant for a missing user_id would otherwise INSERT a PackBalance row
    # whose user_id violates the users FK (500 on Postgres) or orphans (SQLite),
    # diverging from the clean 404 the credits branch already returns.
    u = await session.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="not found")
    # FIX: M7 - re-fetch the user row under FOR UPDATE so two concurrent grant_credits
    # calls (e.g. two admins clicking simultaneously) can't lose each other's
    # increment via a stale read-modify-write. No-op on SQLite; real lock on Postgres.
    await session.refresh(u, with_for_update=True)
    if req.pack == "credits":
        if req.amount < 0 and not await credits.try_consume(session, u, -req.amount, commit=False):  # FIX: AUDIT-4
            raise HTTPException(status_code=409, detail="insufficient credits to deduct")
        if req.amount >= 0:
            await credits.grant(session, u, req.amount, commit=False)  # FIX: M7 - commit with audit below
    elif req.amount >= 0:
        await packs.refund(session, user_id, req.pack, req.amount, commit=False)  # FIX: M7 - commit with audit below
    else:
        if not await packs.try_consume(session, user_id, req.pack, -req.amount, commit=False):
            raise HTTPException(status_code=409, detail="insufficient balance to deduct")
    # FIX: M7 - audit + balance change commit in ONE transaction: a crash between them
    # can't leave a granted balance with no audit trail (or vice versa).
    await audit(session, admin_id=admin.id, action="user.credits", target_type="user",
                target_id=str(user_id), after={"pack": req.pack, "amount": req.amount},
                ip=_client_ip(request), commit=False)
    await session.commit()
    return {"ok": True}


class PremiumRequest(BaseModel):
    months: int
    tier: str = "premium"


@router.post("/{user_id}/premium")
async def grant_premium(
    user_id: int, req: PremiumRequest, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Validate against the real tier set + a sane duration bound. Without this an
    # admin typo writes a junk sub_tier that still reads as is_premium (the property
    # only null-checks) while breaking downstream tier-keyed logic, and an unbounded
    # months feeds an absurd timedelta.
    if req.tier not in SUBSCRIPTION_PRICES:
        raise HTTPException(status_code=400, detail="bad tier")
    if not 1 <= req.months <= 120:
        raise HTTPException(status_code=400, detail="months out of range (1-120)")
    u = await session.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="not found")
    # FIX: R6 - re-fetch under FOR UPDATE so two concurrent grant_premium calls (or a
    # grant racing a webhook activation) can't lose each other's month extension.
    await session.refresh(u, with_for_update=True)
    now = datetime.now(UTC)
    # Normalise tzinfo: SQLite returns naive datetimes, and comparing a naive to an
    # aware datetime raises TypeError. Extend an existing future subscription.
    exp = u.sub_expires
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    base = exp if (exp and exp > now) else now
    u.sub_tier = req.tier
    u.sub_expires = base + timedelta(days=30 * req.months)
    locale = u.language_code
    # FIX: AUDIT12-13 - fold audit into the same tx as the premium grant.
    await audit(session, admin_id=admin.id, action="user.premium", target_type="user",
                target_id=str(user_id), after={"tier": req.tier, "months": req.months},
                ip=_client_ip(request), commit=False)
    await session.commit()
    try:
        await notify_user(user_id, "notify.premium_granted", locale, months=req.months)
    except Exception:  # noqa: BLE001
        import structlog
        structlog.get_logger().warning("admin.grant_premium.notify_failed", user_id=user_id)
    return {"ok": True, "sub_expires": u.sub_expires.isoformat()}


@router.post("/{user_id}/premium/revoke")
async def revoke_premium(
    user_id: int, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Remove a user's Premium immediately and notify them."""
    u = await session.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="not found")
    before = {"sub_tier": u.sub_tier,
              "sub_expires": u.sub_expires.isoformat() if u.sub_expires else None}
    u.sub_tier = None
    u.sub_expires = None
    locale = u.language_code
    # FIX: AUDIT12-14 - fold audit into the same tx as the revoke.
    await audit(session, admin_id=admin.id, action="user.premium_revoke", target_type="user",
                target_id=str(user_id), before=before, ip=_client_ip(request), commit=False)
    await session.commit()
    try:
        await notify_user(user_id, "notify.premium_revoked", locale)
    except Exception:  # noqa: BLE001
        import structlog
        structlog.get_logger().warning("admin.revoke_premium.notify_failed", user_id=user_id)
    return {"ok": True}


@router.post("/{user_id}/reset-quota")
async def reset_quota(
    user_id: int, request: Request,
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    u = await session.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="not found")
    u.text_req_week = 0
    u.text_req_day = 0
    u.mini_app_effects_week = 0
    # FIX: AUDIT-LOW - fold the audit row into the SAME transaction as the mutation
    # (was: commit the reset, then a SECOND commit for audit → a crash between them
    # left the quota reset with no audit record). Matches the M7 atomic-audit pattern.
    await audit(session, admin_id=admin.id, action="user.reset_quota", target_type="user",
                target_id=str(user_id), ip=_client_ip(request), commit=False)
    await session.commit()
    return {"ok": True}


@router.post("/{user_id}/clear-context")
async def clear_user_context(
    user_id: int, request: Request,
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await clear_context(user_id)
    # FIX: AUDIT-LOW - single commit for the audit row (was default commit=True as a
    # standalone second transaction); consistent with the atomic-audit pattern.
    await audit(session, admin_id=admin.id, action="user.clear_context", target_type="user",
                target_id=str(user_id), ip=_client_ip(request), commit=False)
    await session.commit()
    return {"ok": True}


# FIX: AUDIT12-20 - GDPR Art. 17 admin endpoint to fully delete a user's data.
@router.delete("/{user_id}", status_code=200)
async def delete_user(
    user_id: int, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Permanently delete a user and all their data (GDPR Art. 17)."""
    from core.services.gdpr import delete_user_data
    u = await session.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="not found")
    before = {"username": getattr(u, "username", None), "tg_id": getattr(u, "tg_id", None)}
    counts = await delete_user_data(session, user_id)
    await audit(
        session, admin_id=admin.id, action="user.delete_gdpr",
        target_type="user", target_id=str(user_id),
        before=before, after={"counts": counts}, ip=_client_ip(request),
        commit=False,
    )
    await session.commit()
    return {"ok": True, "user_id": user_id, "deleted": counts}
