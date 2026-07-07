"""Admin: metrics / analytics (ТЗ §8) — revenue over a period, new-user trend,
ARPU/ARPPU, conversion, and DAU.

Read-only aggregates over the existing User / Transaction / GenerationJob /
UsageLog tables (no new tables). Queries group by ``func.date()`` so the per-day
series are computed in the DB in a single scan rather than in Python.

Caveats documented inline:
  * Revenue mixes currencies. Transaction.amount is stored in its own unit (stars,
    or minor units for card/SBP gateways). ``revenue_total`` is the plain sum across
    all paid transactions in the window and is therefore expressed in mixed units;
    ``revenue_by_currency`` breaks it down per currency for an honest read. ARPU /
    ARPPU inherit the same mixed-unit caveat.
  * DAU has no dedicated activity log granular enough on its own, so it is the count
    of DISTINCT users with a UsageLog row OR a GenerationJob OR a paid Transaction on
    that calendar day (a usage-based proxy — see ``_dau`` below).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.deps import require_role
from core.db import get_session
from core.models import AdminUser, GenerationJob, Transaction, UsageLog, User
from core.timeutils import ensure_aware

router = APIRouter(prefix="/analytics", tags=["admin-analytics"])


def _window_start(days: int) -> datetime:
    # Inclusive lower bound: include the first calendar day of the window.
    days = max(1, min(days, 365))
    start = datetime.now(UTC) - timedelta(days=days - 1)
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_day(value: str, field: str) -> datetime:
    try:
        return ensure_aware(datetime.fromisoformat(value))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{field} must be ISO date") from None


def _resolve_window(
    days: int, since: str | None, until: str | None
) -> tuple[datetime, datetime, int]:
    """Resolve the reporting window to (start, end, span_days).

    A custom range (``since``/``until`` as YYYY-MM-DD) wins over ``days``; the start
    floors to 00:00 and the end ceils to the last microsecond of its day so both
    boundary days are fully included. Otherwise fall back to the rolling ``days``
    window ending now. Endpoints filter on BOTH bounds so a custom range is closed."""
    now = datetime.now(UTC)
    if since:
        start = _parse_day(since, "since").replace(hour=0, minute=0, second=0, microsecond=0)
        end = (
            _parse_day(until, "until").replace(hour=23, minute=59, second=59, microsecond=999999)
            if until else now
        )
        if end < start:
            raise HTTPException(status_code=400, detail="until must be on/after since")
        span = (end.date() - start.date()).days + 1
        return start, end, span
    days = max(1, min(days, 365))
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now, days


@router.get("/summary")
async def summary(
    days: int = Query(30, ge=1, le=365),
    since: str | None = None,
    until: str | None = None,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Revenue + new-user trend + ARPU/ARPPU + conversion for the window.

    Revenue, ARPU and ARPPU are reported PER CURRENCY (``currencies``) — never summed
    across currencies, since Stars and minor-unit fiat live in different units and a
    combined total would be meaningless. ``revenue_total``/``arpu``/``arppu`` (mixed
    units) are kept only for backward compatibility. paid_users = distinct users with a
    paid tx in the window; ARPU = rev/total_users, ARPPU = rev/paying_users_in_currency.
    """
    start, end, span = _resolve_window(days, since, until)
    paid = (Transaction.status == "paid")
    in_window = (Transaction.created_at >= start) & (Transaction.created_at <= end)

    total_users = await session.scalar(select(func.count()).select_from(User)) or 0

    # Per-currency revenue + paying users → honest ARPU/ARPPU that never crosses units.
    cur_rows = (await session.execute(
        select(
            Transaction.currency,
            func.coalesce(func.sum(Transaction.amount), 0),
            func.count(func.distinct(Transaction.user_id)),
        ).where(paid, in_window).group_by(Transaction.currency)
    )).all()
    currencies: dict[str, dict] = {}
    revenue_by_currency: dict[str, int] = {}
    revenue_total = 0
    for cur, total, pu in cur_rows:
        cur = (cur or "stars").lower()
        total, pu = int(total), int(pu)
        revenue_total += total
        revenue_by_currency[cur] = total
        currencies[cur] = {
            "revenue": total,
            "paid_users": pu,
            "arpu": round(total / total_users, 2) if total_users else 0.0,
            "arppu": round(total / pu, 2) if pu else 0.0,
        }

    rev_day_rows = (await session.execute(
        select(func.date(Transaction.created_at).label("d"),
               func.coalesce(func.sum(Transaction.amount), 0))
        .where(paid, in_window)
        .group_by("d").order_by("d")
    )).all()
    revenue_by_day = [{"date": str(d), "amount": int(a)} for d, a in rev_day_rows]

    new_day_rows = (await session.execute(
        select(func.date(User.created_at).label("d"), func.count())
        .where(User.created_at >= start, User.created_at <= end)
        .group_by("d").order_by("d")
    )).all()
    new_users_by_day = [{"date": str(d), "count": int(n)} for d, n in new_day_rows]

    paid_users = await session.scalar(
        select(func.count(func.distinct(Transaction.user_id))).where(paid, in_window)
    ) or 0

    arpu = round(revenue_total / total_users, 2) if total_users else 0.0
    arppu = round(revenue_total / paid_users, 2) if paid_users else 0.0
    conversion_pct = round(paid_users / total_users * 100, 2) if total_users else 0.0

    return {
        "days": span,
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "currencies": currencies,
        "revenue_total": int(revenue_total),
        "revenue_by_currency": revenue_by_currency,
        "revenue_by_day": revenue_by_day,
        "new_users_by_day": new_users_by_day,
        "paid_users": int(paid_users),
        "total_users": int(total_users),
        "arpu": arpu,
        "arppu": arppu,
        "conversion_pct": conversion_pct,
    }


@router.get("/dau")
async def dau(
    days: int = Query(14, ge=1, le=90),
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Daily Active Users by day.

    PROXY: there is no single fine-grained activity log, so "active on day D" =
    the user produced a UsageLog row OR a GenerationJob OR a paid Transaction on D.
    We UNION the (user_id, date) pairs from the three sources and count DISTINCT
    users per day, so a user active via several signals is counted once.
    """
    start = _window_start(days)

    usage = select(
        UsageLog.user_id.label("user_id"),
        func.date(UsageLog.created_at).label("d"),
    ).where(UsageLog.created_at >= start)
    jobs = select(
        GenerationJob.user_id.label("user_id"),
        func.date(GenerationJob.created_at).label("d"),
    ).where(GenerationJob.created_at >= start)
    txs = select(
        Transaction.user_id.label("user_id"),
        func.date(Transaction.created_at).label("d"),
    ).where(Transaction.status == "paid", Transaction.created_at >= start)

    activity = union(usage, jobs, txs).subquery()
    rows = (await session.execute(
        select(activity.c.d, func.count(func.distinct(activity.c.user_id)))
        .group_by(activity.c.d).order_by(activity.c.d)
    )).all()

    return {
        "days": days,
        "proxy": "usage_log|generation_job|paid_transaction (distinct users/day)",
        "dau_by_day": [{"date": str(d), "count": int(n)} for d, n in rows],
    }


@router.get("/funnel")
async def funnel(
    days: int = Query(30, ge=1, le=365),
    since: str | None = None,
    until: str | None = None,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Signup-cohort funnel (ТЗ §8 «воронка») over users created in the window.

    Each stage counts users who reached AT LEAST that depth, so the funnel is
    strictly nested (registered ⊇ activated ⊇ purchased ⊇ repeat): registered →
    activated (≥1 generation job OR a purchase) → purchased (≥1 paid tx) → repeat
    (≥2 paid tx). Downstream actions are counted lifetime (not windowed), so the
    funnel shows how far the cohort progressed, not just what happened in the window."""
    start, end, days = _resolve_window(days, since, until)
    cohort = (User.created_at >= start) & (User.created_at <= end)

    # Correlated "has ever …" predicates for a cohort user.
    job_exists = (
        select(GenerationJob.user_id)
        .where(GenerationJob.user_id == User.user_id).exists()
    )
    paid_exists = (
        select(Transaction.user_id)
        .where(Transaction.user_id == User.user_id, Transaction.status == "paid")
        .exists()
    )

    registered = await session.scalar(
        select(func.count()).select_from(User).where(cohort)
    ) or 0

    # "activated" = reached activation OR BEYOND. A user can pay WITHOUT ever running
    # a generation (buys Premium immediately, then churns — a top-up/sub creates no
    # GenerationJob). Counting only job_exists would let `purchased` exceed
    # `activated`, widening the funnel at a later stage. Including buyers keeps it
    # monotonically non-increasing without undercounting purchasers.
    activated = await session.scalar(
        select(func.count()).select_from(User)
        .where(cohort, or_(job_exists, paid_exists))
    ) or 0

    purchased = await session.scalar(
        select(func.count()).select_from(User).where(cohort, paid_exists)
    ) or 0

    repeat_buyers = (
        select(Transaction.user_id)
        .where(Transaction.status == "paid")
        .group_by(Transaction.user_id)
        .having(func.count() >= 2)
        .subquery()
    )
    repeat = await session.scalar(
        select(func.count()).select_from(User)
        .where(cohort, User.user_id.in_(select(repeat_buyers.c.user_id)))
    ) or 0

    return {
        "days": days,
        "stages": [
            {"stage": "registered", "count": int(registered)},
            {"stage": "activated", "count": int(activated)},
            {"stage": "purchased", "count": int(purchased)},
            {"stage": "repeat", "count": int(repeat)},
        ],
    }


@router.get("/retention")
async def retention(
    days: int = Query(30, ge=1, le=365),
    since: str | None = None,
    until: str | None = None,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Rolling D1/D7/D30 retention over the windowed signup cohort (ТЗ §8).

    WINDOWED PROXY (mirrors the DAU-proxy caveat): for each k, ``eligible`` = users
    who signed up in [start, now-k] (so they had k days to return); ``retained`` =
    those whose latest activity (UsageLog ∪ GenerationJob ∪ paid Transaction) is on or
    after signup + k days. The created_at + k comparison is done in Python to stay
    portable across SQLite/Postgres (no DB-specific date-interval SQL)."""
    start, end, days = _resolve_window(days, since, until)
    now = datetime.now(UTC)

    users = (await session.execute(
        select(User.user_id, User.created_at)
        .where(User.created_at >= start, User.created_at <= end)
    )).all()

    usage = select(
        UsageLog.user_id.label("uid"), UsageLog.created_at.label("ts"),
    ).where(UsageLog.created_at >= start)
    jobs = select(
        GenerationJob.user_id.label("uid"), GenerationJob.created_at.label("ts"),
    ).where(GenerationJob.created_at >= start)
    txs = select(
        Transaction.user_id.label("uid"), Transaction.created_at.label("ts"),
    ).where(Transaction.status == "paid", Transaction.created_at >= start)
    act = union(usage, jobs, txs).subquery()
    last_active = {
        uid: ts for uid, ts in (await session.execute(
            select(act.c.uid, func.max(act.c.ts)).group_by(act.c.uid)
        )).all()
    }

    out: dict = {"days": days}
    for k in (1, 7, 30):
        cutoff = now - timedelta(days=k)
        eligible = [(uid, a) for uid, c in users if (a := ensure_aware(c)) <= cutoff]
        retained = sum(
            1 for uid, created in eligible
            if (la := last_active.get(uid)) is not None
            and ensure_aware(la) >= created + timedelta(days=k)
        )
        out[f"d{k}"] = round(retained / len(eligible) * 100, 2) if eligible else 0.0
        out[f"eligible_d{k}"] = len(eligible)
    return out


@router.get("/geo")
async def geo(
    days: int = Query(30, ge=1, le=365),
    since: str | None = None,
    until: str | None = None,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Audience geography for users who signed up in the window: top languages
    (always present) and top countries (set only when a phone was shared, so often
    sparse). Both as {code, count}, most-common first."""
    start, end, days = _resolve_window(days, since, until)
    cohort = (User.created_at >= start) & (User.created_at <= end)

    lang_rows = (await session.execute(
        select(User.language_code, func.count())
        .where(cohort, User.language_code.isnot(None), User.language_code != "")
        .group_by(User.language_code).order_by(func.count().desc()).limit(15)
    )).all()
    country_rows = (await session.execute(
        select(User.country, func.count())
        .where(cohort, User.country.isnot(None), User.country != "")
        .group_by(User.country).order_by(func.count().desc()).limit(15)
    )).all()
    return {
        "days": days,
        "top_languages": [{"code": c, "count": int(n)} for c, n in lang_rows],
        "top_countries": [{"code": c, "count": int(n)} for c, n in country_rows],
    }


@router.get("/content")
async def content(
    days: int = Query(30, ge=1, le=365),
    since: str | None = None,
    until: str | None = None,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Top generation content in the window (ТЗ §8 «контент-аналитика»): most-used
    services and model variants, by job count."""
    start, end, days = _resolve_window(days, since, until)
    in_window = (GenerationJob.created_at >= start) & (GenerationJob.created_at <= end)
    cnt = func.count().label("c")

    svc_rows = (await session.execute(
        select(GenerationJob.service, cnt)
        .where(in_window)
        .group_by(GenerationJob.service).order_by(cnt.desc()).limit(15)
    )).all()
    mdl_rows = (await session.execute(
        select(GenerationJob.model_variant, cnt)
        .where(in_window, GenerationJob.model_variant.is_not(None))
        .group_by(GenerationJob.model_variant).order_by(cnt.desc()).limit(15)
    )).all()

    return {
        "days": days,
        "top_services": [{"name": s, "count": int(n)} for s, n in svc_rows],
        "top_models": [{"name": m, "count": int(n)} for m, n in mdl_rows],
    }
