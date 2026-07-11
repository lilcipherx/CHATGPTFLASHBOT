"""Admin: dashboard, payments(+refund), pricing, providers kill-switch,
gate-channels, broadcasts (§11A.2)."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import (  # FIX: B8 - update needed for R7 conditional UPDATE in cancel_broadcast
    func,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError  # FIX: F20 - clean 409 on concurrent create_promo
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.audit import audit
from api.admin.deps import like_contains, require_role
from core.ai_router.video_adapters import _PROVIDERS as VIDEO_PROVIDERS
from core.db import get_session
from core.models import (
    AdminAuditLog,
    AdminUser,
    BotInstance,
    Broadcast,
    ChannelGate,
    GenerationJob,
    Pricing,
    PromoCode,
    Referral,
    Transaction,
    UsageLog,
    User,
)
from core.payments import PaymentError, get_provider
from core.queue import enqueue
from core.redis_client import redis_client
from core.services import feature_flags, gateway_keys, provider_keys, providers_admin
from core.services.billing import revoke_entitlement
from core.timeutils import ensure_aware

router = APIRouter(tags=["admin-ops"])
log = structlog.get_logger()


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


# ---------- Dashboard ----------
# The dashboard aggregates (COUNT(*), SUM(credits), GROUP BY status) are
# inherently sequential scans — no index avoids them on Postgres. Rather than run
# them on every admin page load / poll, cache the whole payload briefly: at 3M+
# rows this turns a burst of refreshes into one scan per TTL window. Stats this
# fresh are fine for an ops dashboard.
_DASHBOARD_CACHE_KEY = "admin:dashboard:v2"
_DASHBOARD_CACHE_TTL = 60  # seconds

# Period selector → window in days for the time-bounded ("flow") aggregates.
# None = all time. Stock metrics (total users, active subs, credits, banned,
# live queue) ignore the period — a window can't change a current total.
_PERIODS: dict[str, int | None] = {"day": 1, "week": 7, "month": 30, "all": None}

# Last-activity proxy: there is no dedicated last_active column, so coalesce the
# best-available write timestamps (mirrors core.services.notify._activity_col).
_ACTIVITY = func.coalesce(User.updated_at, User.last_bonus_at, User.created_at)


@router.get("/dashboard")
async def dashboard(
    period: str = "all",
    admin: AdminUser = Depends(require_role("support")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if period not in _PERIODS:
        period = "all"
    cache_key = f"{_DASHBOARD_CACHE_KEY}:{period}"
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:  # noqa: BLE001 — cache is best-effort; fall through to DB
        pass

    now = datetime.now(UTC)
    window = _PERIODS[period]
    since = now - timedelta(days=window) if window is not None else None
    day_ago, week_ago, month_ago = (
        now - timedelta(days=1), now - timedelta(days=7), now - timedelta(days=30),
    )

    def _in_period(col):
        """Apply the selected window to a time column (no-op for 'all')."""
        return col >= since if since is not None else col.isnot(None)

    # ---- stock (all-time) metrics — independent of the period selector
    total_users = await session.scalar(select(func.count()).select_from(User))
    active_subs = await session.scalar(
        select(func.count()).select_from(User).where(User.sub_expires > now)
    )
    banned_users = await session.scalar(
        select(func.count()).select_from(User).where(User.is_banned.is_(True))
    )
    credits_total = await session.scalar(
        select(func.coalesce(func.sum(User.credits), 0))
    )

    # ---- engagement: DAU / WAU / MAU (active = any row-write in the window)
    dau = await session.scalar(select(func.count()).select_from(User).where(_ACTIVITY >= day_ago))
    wau = await session.scalar(select(func.count()).select_from(User).where(_ACTIVITY >= week_ago))
    mau = await session.scalar(select(func.count()).select_from(User).where(_ACTIVITY >= month_ago))

    # ---- flow (period-bounded) metrics
    new_users = await session.scalar(
        select(func.count()).select_from(User).where(_in_period(User.created_at))
    )
    new_users_7d = await session.scalar(
        select(func.count()).select_from(User).where(User.created_at >= week_ago)
    )
    paid_tx = await session.scalar(
        select(func.count()).select_from(Transaction)
        .where(Transaction.status == "paid", _in_period(Transaction.created_at))
    )
    paying_users = await session.scalar(
        select(func.count(func.distinct(Transaction.user_id)))
        .where(Transaction.status == "paid", _in_period(Transaction.created_at))
    ) or 0
    # Revenue and average check broken out BY CURRENCY (Stars ⭐, RUB ₽, crypto…)
    # never summed across currencies — and within each, by gateway. Summing a Stars
    # amount onto a ruble amount would be meaningless; this keeps every total honest.
    rev_rows = (await session.execute(
        select(
            Transaction.currency, Transaction.gateway,
            func.coalesce(func.sum(Transaction.amount), 0), func.count(),
        )
        .where(Transaction.status == "paid", _in_period(Transaction.created_at))
        .group_by(Transaction.currency, Transaction.gateway)
    )).all()
    revenue_by_currency: dict[str, dict] = {}
    for cur, gw, amount, cnt in rev_rows:
        cur = (cur or "stars").lower()
        bucket = revenue_by_currency.setdefault(cur, {"total": 0, "count": 0, "by_gateway": {}})
        bucket["total"] += int(amount)
        bucket["count"] += int(cnt)
        bucket["by_gateway"][gw] = bucket["by_gateway"].get(gw, 0) + int(amount)
    for bucket in revenue_by_currency.values():
        bucket["avg_check"] = round(bucket["total"] / bucket["count"]) if bucket["count"] else 0

    # Legacy flat gateway map (kept for any older consumer): native amounts summed
    # per gateway. Prefer revenue_by_currency above for anything user-facing.
    revenue_by_gateway: dict[str, int] = {}
    for bucket in revenue_by_currency.values():
        for gw, amt in bucket["by_gateway"].items():
            revenue_by_gateway[gw] = revenue_by_gateway.get(gw, 0) + amt

    job_rows = (await session.execute(
        select(GenerationJob.status, func.count())
        .where(_in_period(GenerationJob.created_at)).group_by(GenerationJob.status)
    )).all()
    jobs_by_status = {s: int(n) for s, n in job_rows}
    # Live queue depth is a stock metric — always current, ignores the window.
    live_q = (await session.execute(
        select(GenerationJob.status, func.count())
        .where(GenerationJob.status.in_(("pending", "processing")))
        .group_by(GenerationJob.status)
    )).all()
    pending_jobs = sum(int(n) for _, n in live_q)

    conversion = round(paying_users / total_users * 100, 2) if total_users else 0.0

    result = {
        "period": period,
        "total_users": total_users or 0,
        "new_users": new_users or 0,
        "new_users_7d": new_users_7d or 0,
        "active_subscriptions": active_subs or 0,
        "banned_users": banned_users or 0,
        "credits_total": int(credits_total or 0),
        "paid_transactions": paid_tx or 0,
        "paying_users": paying_users,
        "conversion_pct": conversion,
        "dau": dau or 0,
        "wau": wau or 0,
        "mau": mau or 0,
        "revenue_by_currency": revenue_by_currency,
        "revenue_by_gateway": revenue_by_gateway,
        "jobs_by_status": jobs_by_status,
        "completed_generations": jobs_by_status.get("complete", 0),
        "pending_jobs": pending_jobs,
    }
    try:
        await redis_client.set(cache_key, json.dumps(result), ex=_DASHBOARD_CACHE_TTL)
    except Exception:  # noqa: BLE001 — caching is best-effort
        pass
    return result


# ---------- Payments ----------
# Statuses considered a completed/keep-access sale (vs. failed/pending/refunded).
_PAID = "paid"


def _parse_dt(value: str, field: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{field} must be ISO 8601") from None
    return ensure_aware(dt)


def _serialize_tx(t: Transaction) -> dict:
    """Full transaction view for the payments control center. Exposes the columns
    that already exist on the row (duration/qty/credits/paid_at/gateway ref) so the
    detail drawer is informative — no migration. ``gateway_tx_id`` is a reconciliation
    reference (not a credential)."""
    return {
        "tx_id": str(t.tx_id), "user_id": t.user_id, "product": t.product,
        "duration_months": t.duration_months, "qty": t.qty,
        "amount": t.amount, "currency": t.currency, "gateway": t.gateway,
        "gateway_tx_id": t.gateway_tx_id, "status": t.status,
        "credits_added": t.credits_added,
        "created_at": t.created_at.isoformat(),
        "paid_at": t.paid_at.isoformat() if t.paid_at else None,
    }


@router.get("/payments")
async def list_payments(
    status: str | None = None,
    gateway: str | None = None,
    user_id: int | None = None,
    since: str | None = None,   # ISO date/datetime — only tx at/after this
    until: str | None = None,   # ISO date/datetime — only tx before this
    limit: int = 100,
    offset: int = 0,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Filtered, paginated transaction list (newest first). All filters hit indexed
    columns (status / gateway / user_id / created_at), so this stays usable at scale.
    Returns the page plus the total matching count for the pager."""
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    filters = []
    if status:
        filters.append(Transaction.status == status)
    if gateway:
        filters.append(Transaction.gateway == gateway)
    if user_id is not None:
        filters.append(Transaction.user_id == user_id)
    if since:
        filters.append(Transaction.created_at >= _parse_dt(since, "since"))
    if until:
        filters.append(Transaction.created_at < _parse_dt(until, "until"))

    total = int(await session.scalar(
        select(func.count()).select_from(Transaction).where(*filters)
    ) or 0)
    rows = (await session.scalars(
        select(Transaction).where(*filters)
        .order_by(Transaction.created_at.desc())
        .limit(limit).offset(offset)
    )).all()
    return {
        "items": [_serialize_tx(t) for t in rows],
        "total": total, "limit": limit, "offset": offset,
        "has_more": offset + len(rows) < total,
    }


@router.get("/payments/stats")
async def payments_stats(
    days: int = 30,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Accurate, currency-aware payment aggregates over the last ``days`` — computed
    in the DB across the WHOLE window (not just one page), so the gateway table and
    KPIs are correct at any volume.

    Revenue mixes currencies (Transaction.amount is in its own unit: Stars, or minor
    units for card/SBP). We therefore never sum a single cross-currency total —
    revenue is always broken down ``by_currency``; ``revenue_by_day`` carries the same
    mixed-unit caveat and is only meaningful read per-currency."""
    days = max(1, min(days, 365))
    start = (datetime.now(UTC) - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    in_window = (Transaction.created_at >= start)
    paid = (Transaction.status == _PAID)

    status_rows = (await session.execute(
        select(Transaction.status, func.count())
        .where(in_window).group_by(Transaction.status)
    )).all()
    by_status = {s: int(n) for s, n in status_rows}
    total = sum(by_status.values())

    rev_cur_rows = (await session.execute(
        select(Transaction.currency, func.coalesce(func.sum(Transaction.amount), 0), func.count())
        .where(in_window, paid).group_by(Transaction.currency)
    )).all()
    revenue_by_currency = {c: int(s) for c, s, _n in rev_cur_rows}
    # Average paid amount per currency (never cross-currency) — honest "средний чек".
    avg_check_by_currency = {
        c: (round(int(s) / int(n)) if n else 0) for c, s, n in rev_cur_rows
    }

    rev_day_rows = (await session.execute(
        select(func.date(Transaction.created_at).label("d"),
               func.coalesce(func.sum(Transaction.amount), 0), func.count())
        .where(in_window, paid).group_by("d").order_by("d")
    )).all()
    revenue_by_day = [{"date": str(d), "amount": int(a), "count": int(n)}
                      for d, a, n in rev_day_rows]

    # Per-gateway: total / paid counts, last activity, and paid revenue per currency.
    gw_rows = (await session.execute(
        select(Transaction.gateway, Transaction.status, func.count(),
               func.max(Transaction.created_at))
        .where(in_window).group_by(Transaction.gateway, Transaction.status)
    )).all()
    gw_rev_rows = (await session.execute(
        select(Transaction.gateway, Transaction.currency,
               func.coalesce(func.sum(Transaction.amount), 0))
        .where(in_window, paid).group_by(Transaction.gateway, Transaction.currency)
    )).all()
    gws: dict[str, dict] = {}
    for gw, st, n, last in gw_rows:
        g = gws.setdefault(gw, {"gateway": gw, "count": 0, "paid": 0,
                                "revenue_by_currency": {}, "last_at": None})
        g["count"] += int(n)
        if st == _PAID:
            g["paid"] += int(n)
        last_iso = last.isoformat() if last else None
        if last_iso and (g["last_at"] is None or last_iso > g["last_at"]):
            g["last_at"] = last_iso
    for gw, cur, s in gw_rev_rows:
        gws.setdefault(gw, {"gateway": gw, "count": 0, "paid": 0,
                            "revenue_by_currency": {}, "last_at": None})
        gws[gw]["revenue_by_currency"][cur] = int(s)
    by_gateway = []
    for g in gws.values():
        g["success_pct"] = round(g["paid"] / g["count"] * 100, 1) if g["count"] else 0.0
        by_gateway.append(g)
    by_gateway.sort(key=lambda g: (g["paid"], g["count"]), reverse=True)

    paid_users = int(await session.scalar(
        select(func.count(func.distinct(Transaction.user_id)))
        .where(in_window, paid)
    ) or 0)

    return {
        "days": days,
        "totals": {
            "count": total,
            "paid": by_status.get("paid", 0),
            "failed": by_status.get("failed", 0),
            "pending": by_status.get("pending", 0),
            "refunded": by_status.get("refunded", 0),
            "refund_pending": by_status.get("refund_pending", 0),
        },
        "by_status": by_status,
        "by_gateway": by_gateway,
        "revenue_by_currency": revenue_by_currency,
        "avg_check_by_currency": avg_check_by_currency,
        "revenue_by_day": revenue_by_day,
        "paid_users": paid_users,
    }


@router.post("/payments/{tx_id}/refund")
async def refund_payment(
    tx_id: str, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Refund a paid transaction. Two-phase + retryable:

    1. On the first call (status='paid') the entitlement is revoked exactly once
       and the tx moves to 'refund_pending' — the user immediately loses access.
    2. The money refund is then attempted at the gateway. On success the tx moves
       to 'refunded'; on failure it STAYS 'refund_pending' so this endpoint can be
       called again to retry the gateway refund (without re-revoking).
    """
    try:
        tx_pk = uuid.UUID(tx_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="not found") from None
    tx = await session.get(Transaction, tx_pk)
    if tx is None:
        raise HTTPException(status_code=404, detail="not found")
    # Serialize concurrent / duplicate refund requests for the SAME tx by locking
    # the row (SELECT ... FOR UPDATE) and re-reading the status under the lock.
    # Without this, two near-simultaneous clicks both read status='paid', both
    # revoke the entitlement (double-subtracting the months/credits) AND both call
    # the gateway refund — and YooKassa/Stripe do NOT dedupe two separate refund
    # calls (YooKassa even mints a fresh idempotence key each call), so the user is
    # refunded twice. The lock is held across Phase 2 (a single commit at the end),
    # so the gateway call can't run concurrently either. It is per-row, so only
    # refunds of this exact tx wait — unrelated refunds are unaffected.
    await session.refresh(tx, with_for_update=True)
    if tx.status == "refunded":
        raise HTTPException(status_code=400, detail="already refunded")
    if tx.status not in ("paid", "refund_pending"):
        raise HTTPException(status_code=400, detail="not refundable")

    before = {"status": tx.status, "amount": tx.amount, "currency": tx.currency, "gateway": tx.gateway, "gateway_tx_id": tx.gateway_tx_id}  # FIX: AUDIT-102
    # Phase 1 — revoke the entitlement exactly once (only when coming from 'paid';
    # a retry is already in refund_pending with the entitlement gone). NOT committed
    # here: the row lock is deliberately held through Phase 2 below.
    if tx.status == "paid":
        await revoke_entitlement(session, tx)
        tx.status = "refund_pending"

    # Phase 2 — attempt the money refund at the gateway, still under the row lock.
    ok, detail = await _refund_at_gateway(tx)
    if ok:
        tx.status = "refunded"
    # FIX: AUDIT12-12 - fold the audit insert INTO the same transaction as the
    # refund commit (was: audit ran in a SEPARATE tx with commit=True, so a DB
    # hiccup between the two left a refund with no audit trail).
    await audit(session, admin_id=admin.id, action="payment.refund", target_type="transaction",
                target_id=tx_id, before=before,
                after={"status": tx.status, "gateway_refund": detail}, ip=_ip(request),
                commit=False)
    # Single commit releases the lock with the final consistent state: 'refunded'
    # on success, or 'refund_pending' (entitlement already revoked) on gateway
    # failure, so this endpoint can be called again to retry the money refund.
    await session.commit()
    return {
        "ok": ok,
        "status": tx.status,            # 'refunded' | 'refund_pending'
        "entitlement_revoked": True,
        "gateway_refund": detail,       # 'stars' | 'skip' | 'refunded:<id>' | error text
        "retryable": not ok,            # call this endpoint again to retry the money refund
    }


async def _refund_at_gateway(tx: Transaction) -> tuple[bool, str]:
    """Issue the money refund at the gateway. Returns (ok, detail).

    ok=True only when the money is confirmed returned (or there is nothing to
    return — a Stars tx with no charge id). On any failure ok=False and the caller
    keeps the tx in 'refund_pending' for a later retry."""
    if tx.gateway == "stars":
        if not tx.gateway_tx_id:
            return True, "skip"  # nothing captured at the gateway to return
        from core.bot_client import get_bot

        try:
            await get_bot().refund_star_payment(
                user_id=tx.user_id, telegram_payment_charge_id=tx.gateway_tx_id
            )
            return True, "stars"
        except Exception as exc:  # noqa: BLE001 — retryable
            log.warning("refund.stars_failed", tx=str(tx.tx_id), error=str(exc))
            return False, f"stars_failed: {exc}"

    # External card/SBP gateways: call the provider's live refund API.
    provider = get_provider(tx.gateway)
    if provider is None or not provider.is_available() or not tx.gateway_tx_id:
        log.warning("refund.gateway_unavailable", gateway=tx.gateway, tx=str(tx.tx_id))
        return False, "manual_required"
    try:
        refund_id = await provider.refund(gateway_tx_id=tx.gateway_tx_id, amount=tx.amount)
        log.info("refund.gateway_ok", gateway=tx.gateway, tx=str(tx.tx_id), refund=refund_id)
        return True, f"refunded:{refund_id}" if refund_id else "refunded"
    except PaymentError as exc:
        log.warning("refund.gateway_failed", gateway=tx.gateway, tx=str(tx.tx_id), error=str(exc))
        return False, f"failed: {exc}"


# ---------- Pricing (superadmin) ----------
@router.get("/pricing")
async def get_pricing(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rows = (await session.scalars(select(Pricing))).all()
    return {r.key: r.value for r in rows}


class PricingUpdate(BaseModel):
    value: dict


@router.put("/pricing/{key}")
async def set_pricing(
    key: str, req: PricingUpdate, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await session.get(Pricing, key)
    before = row.value if row else None
    if row is None:
        session.add(Pricing(key=key, value=req.value))
    else:
        row.value = req.value
    await audit(session, admin_id=admin.id, action="pricing.update", target_type="pricing",
                target_id=key, before=before, after=req.value, ip=_ip(request), commit=False)
    await session.commit()
    return {"ok": True}


# ---------- Feature flags ----------
@router.get("/flags")
async def get_flags(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    flags = await feature_flags.get_flags(session)
    return [
        {"key": k, "enabled": flags.get(k, default), "label": label, "default": default}
        for k, (default, label) in feature_flags.DEFAULTS.items()
    ]


class FlagUpdate(BaseModel):
    enabled: bool


@router.put("/flags/{key}")
async def set_flag(
    key: str, req: FlagUpdate, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if key not in feature_flags.DEFAULTS:
        raise HTTPException(status_code=400, detail="unknown flag")
    await feature_flags.set_flag(session, key, req.enabled)
    await audit(session, admin_id=admin.id, action="flag.set", target_type="flag",
                target_id=key, after={"enabled": req.enabled}, ip=_ip(request))
    return {"ok": True, "key": key, "enabled": req.enabled}


# ---------- Providers kill-switch ----------
@router.get("/providers")
async def list_providers(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    from core.ai_router.image_adapters import _IMAGE_PROVIDERS
    from core.ai_router.music_adapters import _PROVIDERS as MUSIC_PROVIDERS

    disabled = set(await providers_admin.get_disabled(session))
    # All media-generation providers across modalities; the kill-switch (toggle) is
    # enforced by the media router (resolve_backends / generate_image_routed_managed).
    registries = [
        ("video", VIDEO_PROVIDERS), ("image", _IMAGE_PROVIDERS), ("music", MUSIC_PROVIDERS),
    ]
    return [
        {"key": key, "available": prov.is_available(),
         "disabled": key in disabled, "modality": modality}
        for modality, registry in registries
        for key, prov in registry.items()
    ]


@router.post("/providers/{key}/toggle")
async def toggle_provider(
    key: str, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now_disabled = await providers_admin.toggle(session, key)
    await audit(session, admin_id=admin.id, action="provider.toggle", target_type="provider",
                target_id=key, after={"disabled": now_disabled}, ip=_ip(request))
    return {"key": key, "disabled": now_disabled}


# ---------- Native provider API keys ----------
@router.get("/provider-keys")
async def list_provider_keys(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Per-provider key status (masked — never returns a full key)."""
    return await provider_keys.get_status(session)


class ProviderKeysReq(BaseModel):
    # {provider_name: api_key}. Empty values are ignored (keep existing key).
    keys: dict[str, str]


@router.put("/provider-keys")
async def set_provider_keys(
    req: ProviderKeysReq, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    changed = await provider_keys.set_keys(session, req.keys)
    if changed:
        # Audit WHICH providers changed — never the key values themselves.
        await audit(session, admin_id=admin.id, action="provider.key.set",
                    target_type="provider_key", target_id=",".join(changed),
                    after={"changed": changed}, ip=_ip(request), commit=False)
    await session.commit()
    return {"ok": True, "changed": changed}


@router.post("/provider-keys/{name}/test")
async def test_provider_key(
    name: str, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Online probe: hit the provider's API with its current key and report OK/error
    + latency. Read-only; the key is never returned. Audited (which provider, result)."""
    result = await provider_keys.test_key(session, name)
    await audit(session, admin_id=admin.id, action="provider.key.test", target_type="provider_key",
                target_id=name, after={"ok": result["ok"], "status": result["status_code"]},
                ip=_ip(request))
    return result


@router.delete("/provider-keys/{name}")
async def clear_provider_key(
    name: str, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    existed = await provider_keys.clear_key(session, name)
    if existed:
        await audit(session, admin_id=admin.id, action="provider.key.clear",
                    target_type="provider_key", target_id=name, ip=_ip(request))
    return {"ok": True, "cleared": existed}


# ---------- Payment gateway credentials (Stripe / YooKassa / CryptoBot / Tribute) ----------
@router.get("/payments/gateways")
async def list_payment_gateways(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Per-gateway credential status (secrets masked — never returns a full secret)."""
    return await gateway_keys.get_status(session)


class GatewayKeysReq(BaseModel):
    # {settings_field: value}. Empty values are ignored (keep the existing value).
    fields: dict[str, str]


@router.put("/payments/gateways")
async def set_payment_gateways(
    req: GatewayKeysReq, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    changed = await gateway_keys.set_fields(session, req.fields)
    if changed:
        # Audit WHICH fields changed — never the secret values themselves.
        await audit(session, admin_id=admin.id, action="payment.gateway.set",
                    target_type="payment_gateway", target_id=",".join(changed),
                    after={"changed": changed}, ip=_ip(request), commit=False)
    await session.commit()
    return {"ok": True, "changed": changed}


@router.delete("/payments/gateways/{field}")
async def clear_payment_gateway(
    field: str, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    existed = await gateway_keys.clear_field(session, field)
    if existed:
        await audit(session, admin_id=admin.id, action="payment.gateway.clear",
                    target_type="payment_gateway", target_id=field, ip=_ip(request))
    return {"ok": True, "cleared": existed}


@router.get("/provider-base-url")
async def get_openai_base_url(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await provider_keys.get_openai_base_url(session)


class OpenAIBaseUrlReq(BaseModel):
    url: str = ""   # blank reverts to the .env default


@router.put("/provider-base-url")
async def set_openai_base_url(
    req: OpenAIBaseUrlReq, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    url = req.url.strip()
    if url:
        # Same SSRF defence as the per-account base_url setter (ai_routing): the
        # OpenAI client makes server-side calls to this URL carrying the API key in
        # the Authorization header, so an unchecked value could exfiltrate the key
        # to an attacker host or hit the cloud metadata endpoint / internal
        # services. Enforce the AI_BASE_URL_ALLOWLIST (or, unset, reject non-public
        # IPs) — a prefix check alone was insufficient. Single source of truth.
        # FIX: SKILL-AI20 - use the ASYNC variant so DNS resolution runs in a
        # worker thread with a 5s timeout (via asyncio.wait_for inside
        # _validate_base_url_async). The sync _validate_base_url has NO timeout
        # now (AI-20 removed socket.setdefaulttimeout), so calling it from this
        # async endpoint would block the event loop on slow DNS.
        from api.admin.ai_routing import _validate_base_url_async

        url = await _validate_base_url_async(url)
    value = await provider_keys.set_openai_base_url(session, url)
    await audit(session, admin_id=admin.id, action="provider.base_url.set",
                target_type="provider_key", target_id="openai_base_url",
                after={"url": value}, ip=_ip(request))
    return {"ok": True, "value": value}


# ---------- Suno base URL + model (music) — FIX: AUDIT13-M2 ----------
@router.get("/suno-config")
async def get_suno_config(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await provider_keys.get_suno_config(session)


class SunoConfigReq(BaseModel):
    base_url: str = Field("", max_length=2048)   # blank reverts to the .env default
    model: str = Field("", max_length=128)       # blank reverts to the .env default


@router.put("/suno-config")
async def set_suno_config(
    req: SunoConfigReq, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    url = req.base_url.strip()
    if url:
        # Same SSRF defence as the OpenAI base-url setter: the music adapter makes
        # server-side calls to this URL carrying the Suno API key, so validate the
        # resolved host against the allowlist / reject non-public addresses.
        from api.admin.ai_routing import _validate_base_url_async

        url = await _validate_base_url_async(url)
    value = await provider_keys.set_suno_config(session, url, req.model)
    await audit(session, admin_id=admin.id, action="provider.suno_config.set",
                target_type="provider_key", target_id="suno",
                after=value, ip=_ip(request))
    return {"ok": True, **value}


# ---------- Moderation stop-words ----------
@router.get("/moderation-words")
async def list_moderation_words(
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from core.services import moderation

    return {"words": await moderation.get_custom_words(session)}


class ModerationWordsReq(BaseModel):
    # Each rule is {value, type} (type: substring|exact|regex); plain strings are
    # accepted as substring rules for backward compatibility.
    words: list


@router.put("/moderation-words")
async def set_moderation_words(
    req: ModerationWordsReq, request: Request,
    admin: AdminUser = Depends(require_role("moderator")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from core.services import moderation

    words = await moderation.set_custom_words(session, req.words)
    await audit(session, admin_id=admin.id, action="moderation.words.set",
                target_type="moderation", target_id="words",
                after={"count": len(words)}, ip=_ip(request))
    return {"words": words}


# ---------- Gate channels ----------
class GateRequest(BaseModel):
    channel: str
    is_active: bool = True


@router.get("/gates")
async def list_gates(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (await session.scalars(select(ChannelGate))).all()
    return [{"channel": g.channel, "is_active": g.is_active} for g in rows]


@router.put("/gates")
async def upsert_gate(
    req: GateRequest, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),  # FIX: SUPERADMIN-5 - feature gates control who can access which bot features; superadmin-only
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await session.get(ChannelGate, req.channel)
    if row is None:
        session.add(ChannelGate(channel=req.channel, is_active=req.is_active))
    else:
        row.is_active = req.is_active
    await session.commit()
    # FIX: F27 - invalidate every per-user gate-ok cache so a newly-added/activated
    # channel takes effect immediately (otherwise users bypass it for up to 1h).
    from core.services import gate as gate_svc
    await gate_svc.clear_all_caches()
    await audit(session, admin_id=admin.id, action="gate.upsert", target_type="gate",
                target_id=req.channel, after={"is_active": req.is_active}, ip=_ip(request))
    return {"ok": True}


@router.post("/gates/{channel}/check")
async def check_gate(
    channel: str,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Verify the bot can actually enforce this gate: it must be an ADMINISTRATOR of
    the channel (otherwise the subscription check silently passes everyone). Reports
    bot-admin status + subscriber count + title. Read-only Telegram API call."""
    from core.bot_client import get_bot

    bot = get_bot()
    try:
        chat = await bot.get_chat(channel)
        me = await bot.get_me()
        member = await bot.get_chat_member(channel, me.id)
        is_admin = getattr(member, "status", "") in ("administrator", "creator")
        try:
            members = await bot.get_chat_member_count(channel)
        except Exception:  # noqa: BLE001 — count is best-effort
            members = None
        return {
            "ok": True, "bot_is_admin": is_admin, "members": members,
            "title": getattr(chat, "title", None) or channel,
            "detail": "" if is_admin
            else "Бот не админ канала — гейт не сработает (добавьте бота в администраторы).",
        }
    except Exception as exc:  # noqa: BLE001 — bad channel / bot not a member / API error
        return {"ok": False, "bot_is_admin": False, "members": None, "title": "",
                "detail": str(exc)[:200]}


@router.delete("/gates/{channel}")
async def delete_gate(
    channel: str, request: Request,
    admin: AdminUser = Depends(require_role("superadmin")),  # FIX: SUPERADMIN-6 - removing a gate re-opens a feature to everyone; superadmin-only
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Remove a gate channel entirely (vs. just deactivating it). Idempotent."""
    row = await session.get(ChannelGate, channel)
    if row is not None:
        await session.delete(row)
        await session.commit()
        # FIX: F27 - same cache invalidation as upsert_gate.
        from core.services import gate as gate_svc
        await gate_svc.clear_all_caches()
    await audit(session, admin_id=admin.id, action="gate.delete", target_type="gate",
                    target_id=channel, ip=_ip(request))
    return {"ok": True, "deleted": row is not None}


# ---------- Broadcasts ----------
class BroadcastRequest(BaseModel):
    segment: dict
    # FIX: AUDIT13-M9 - cap the body. Telegram rejects >4096 chars, and an unbounded
    # value would be stored + enqueued to the whole audience before every send fails.
    text: str = Field(..., max_length=4096)
    photo_url: str | None = Field(None, max_length=2048)
    button_text: str | None = Field(None, max_length=128)
    button_url: str | None = Field(None, max_length=2048)
    scheduled_at: str | None = None   # ISO datetime; future = scheduled send
    # Campaign metadata — stored in content, ignored by the worker (it reads only
    # text/photo_url/button_*); surfaced back in the admin history + view modal.
    title: str | None = Field(None, max_length=200)
    comment: str | None = Field(None, max_length=2000)
    description: str | None = Field(None, max_length=2000)


@router.get("/broadcasts")
async def list_broadcasts(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (await session.scalars(
        select(Broadcast).order_by(Broadcast.created_at.desc()).limit(50)
    )).all()
    # Resolve author display names in one round-trip (admin_id -> email).
    author_ids = {b.admin_id for b in rows}
    authors: dict[int, str] = {}
    if author_ids:
        for aid, email in (await session.execute(
            select(AdminUser.id, AdminUser.email).where(AdminUser.id.in_(author_ids))
        )).all():
            authors[aid] = email
    return [
        {"id": b.id, "status": b.status, "sent": b.sent, "failed": b.failed,
         "segment": b.segment, "content": b.content,
         "scheduled_at": b.scheduled_at.isoformat() if b.scheduled_at else None,
         "admin_id": b.admin_id, "author": authors.get(b.admin_id),
         "created_at": b.created_at.isoformat()}
        for b in rows
    ]


class EstimateRequest(BaseModel):
    segment: dict


@router.post("/broadcasts/estimate")
async def estimate_broadcast(
    req: EstimateRequest,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """How many users the current segment would reach (banned always excluded).

    Uses the exact same predicate as the worker (`_segment_filter`) so the preview
    never disagrees with the real send."""
    from workers.broadcast_tasks import _segment_filter

    stmt = _segment_filter(select(func.count()).select_from(User), dict(req.segment or {}))
    total = await session.scalar(stmt)
    return {"count": int(total or 0)}


@router.post("/broadcasts/{broadcast_id}/cancel")
async def cancel_broadcast(
    broadcast_id: int, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Only a scheduled (not-yet-enqueued) broadcast can be cancelled. Once it is
    # 'queued'/'sending'/'done' the worker owns it. dispatch_scheduled_broadcasts
    # only claims status=='scheduled', so flipping it to 'cancelled' removes it
    # from the beat cron cleanly with no race.
    bc = await session.get(Broadcast, broadcast_id)
    if bc is None:
        raise HTTPException(status_code=404, detail="broadcast not found")
    if bc.status != "scheduled":
        raise HTTPException(status_code=409, detail="only scheduled broadcasts can be cancelled")
    # FIX: R7 - conditional UPDATE WHERE status='scheduled' so a beat tick that flipped
    # the row to 'queued' between our read and our write is detected (rowcount==0) and
    # we report a 409 instead of overwriting the queued status.
    res = await session.execute(
        update(Broadcast)
        .where(Broadcast.id == broadcast_id, Broadcast.status == "scheduled")
        .values(status="cancelled")
    )
    if res.rowcount == 0:
        await session.rollback()
        raise HTTPException(status_code=409, detail="broadcast was already dispatched")
    await audit(session, admin_id=admin.id, action="broadcast.cancel",
                target_type="broadcast", target_id=str(bc.id), ip=_ip(request), commit=False)
    await session.commit()
    return {"id": bc.id, "status": "cancelled"}


@router.post("/broadcasts")
async def create_broadcast(
    req: BroadcastRequest, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Parse an optional scheduled time; only a FUTURE time defers the send.
    run_at: datetime | None = None
    if req.scheduled_at:
        try:
            run_at = datetime.fromisoformat(req.scheduled_at.replace("Z", "+00:00"))
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=UTC)
        except ValueError:
            raise HTTPException(status_code=400, detail="bad scheduled_at") from None
    deferred = run_at is not None and run_at > datetime.now(UTC)

    # FIX: AUDIT13-M7 - validate button_url scheme before it is stored and rendered as
    # an InlineKeyboardButton(url=...) for the ENTIRE broadcast audience. channel.py and
    # banners.py already gate their link URLs; create_broadcast did not, so a
    # javascript:/data:/malformed value would be pushed to every user.
    _button_url = (req.button_url or "").strip()
    if _button_url and not _button_url.lower().startswith(("http://", "https://", "tg://")):
        raise HTTPException(status_code=400, detail="button_url must be an http(s) or tg:// URL")

    content = {
        "text": req.text,
        "photo_url": (req.photo_url or "").strip() or None,
        "button_text": (req.button_text or "").strip() or None,
        "button_url": _button_url or None,
        "title": (req.title or "").strip() or None,
        "comment": (req.comment or "").strip() or None,
        "description": (req.description or "").strip() or None,
    }
    # Immediate sends are 'queued' from birth (the worker accepts queued and flips it
    # to 'sending') so the history never flashes a misleading "Запланирована" badge in
    # the window before the worker picks the row up. Deferred sends stay 'scheduled'
    # until the dispatch_scheduled_broadcasts beat cron claims them.
    bc = Broadcast(
        admin_id=admin.id, segment=req.segment, content=content,
        scheduled_at=run_at if deferred else None,
        status="scheduled" if deferred else "queued",
    )
    # FIX: AUDIT-100 - enqueue BEFORE commit so Redis failure rolls back
    session.add(bc)
    # FIX: AUDIT-FINAL-6 - flush so bc.id (autoincrement PK) is populated before
    # we hand it to enqueue. Without the flush, bc.id is None at this point and
    # the worker would receive run_broadcast(None) → silent drop. The subsequent
    # commit() still owns the final transaction boundary.
    if not deferred:
        try:
            await session.flush()
            await enqueue("run_broadcast", bc.id)
        except Exception:
            bc.status = "scheduled"  # let beat cron pick it up
    await session.commit()
    await audit(session, admin_id=admin.id, action="broadcast.create", target_type="broadcast",
                target_id=str(bc.id),
                after={"segment": req.segment, "scheduled": deferred}, ip=_ip(request))
    return {"id": bc.id, "status": "scheduled" if deferred else "queued"}


# ---------- Audit log (read) ----------
def _audit_dt(value: str, field: str = "since") -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{field} must be ISO 8601") from None


async def _admin_directory(session: AsyncSession, ids: set[int]) -> dict[int, tuple[str, str]]:
    """admin_id -> (email, role) in one round-trip, for enriching audit rows."""
    if not ids:
        return {}
    return {
        aid: (email, role)
        for aid, email, role in (await session.execute(
            select(AdminUser.id, AdminUser.email, AdminUser.role)
            .where(AdminUser.id.in_(ids))
        )).all()
    }


def _audit_filters(
    action: str | None, admin_id: int | None, target_type: str | None,
    target_id: str | None, q: str | None, since: str | None, until: str | None,
) -> list:
    """Build the WHERE clause for an audit query — shared by the JSON list endpoint
    and the full CSV export so their filters can never drift apart."""
    filters = []
    if action:
        filters.append(AdminAuditLog.action.ilike(like_contains(action), escape="\\"))
    if admin_id is not None:
        filters.append(AdminAuditLog.admin_id == admin_id)
    if target_type:
        filters.append(AdminAuditLog.target_type == target_type)
    if target_id:
        filters.append(AdminAuditLog.target_id == target_id)
    if q:
        like = like_contains(q)
        filters.append(
            AdminAuditLog.action.ilike(like, escape="\\")
            | AdminAuditLog.target_id.ilike(like, escape="\\")
            | AdminAuditLog.ip.ilike(like, escape="\\")
        )
    if since:
        filters.append(AdminAuditLog.created_at >= _audit_dt(since, "since"))
    if until:
        filters.append(AdminAuditLog.created_at < _audit_dt(until, "until"))
    return filters


@router.get("/audit")
async def list_audit(
    action: str | None = None,
    admin_id: int | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    q: str | None = None,        # free-text across action / target_id / ip
    since: str | None = None,    # ISO — only entries at/after this
    until: str | None = None,    # ISO — only entries before this
    limit: int = 100,
    offset: int = 0,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Recent audit entries, newest first, with rich filters (ТЗ §8). Each row is
    enriched with the acting admin's email/role and the stored before/after snapshots
    so the Audit Center can render diffs and a full-event view — no migration (these
    columns already exist). Ordered by the PK (monotonic with insertion time) so the
    sort is index-backed at scale; `created_at` filters still apply."""
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    filters = _audit_filters(action, admin_id, target_type, target_id, q, since, until)

    rows = (await session.scalars(
        select(AdminAuditLog).where(*filters)
        .order_by(AdminAuditLog.id.desc()).limit(limit).offset(offset)
    )).all()
    directory = await _admin_directory(session, {a.admin_id for a in rows})
    out = []
    for a in rows:
        email, role = directory.get(a.admin_id, (None, None))
        out.append({
            "id": a.id, "admin_id": a.admin_id,
            "admin_email": email, "admin_role": role,
            "action": a.action, "target_type": a.target_type, "target_id": a.target_id,
            "before": a.before, "after": a.after,
            "ip": a.ip, "created_at": a.created_at.isoformat(),
        })
    return out


@router.get("/audit/stats")
async def audit_stats(
    days: int = 30,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Audit Center dashboard aggregates over the last ``days`` (plus absolute
    total/today/last-hour counters). All from admin_audit_log + admin_users — no new
    tables. Category/verb buckets are folded from a GROUP BY action in the DB."""
    days = max(1, min(days, 365))
    now = datetime.now(UTC)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    hour0 = now - timedelta(hours=1)

    def _count_since(ts):
        return select(func.count()).select_from(AdminAuditLog).where(AdminAuditLog.created_at >= ts)

    total = int(await session.scalar(select(func.count()).select_from(AdminAuditLog)) or 0)
    today = int(await session.scalar(_count_since(today0)) or 0)
    last_hour = int(await session.scalar(_count_since(hour0)) or 0)
    last_action_at = await session.scalar(select(func.max(AdminAuditLog.created_at)))
    distinct_admins = int(await session.scalar(
        select(func.count(func.distinct(AdminAuditLog.admin_id)))
        .where(AdminAuditLog.created_at >= start)) or 0)
    admins_total = int(await session.scalar(select(func.count()).select_from(AdminUser)) or 0)
    last_login_at = await session.scalar(select(func.max(AdminUser.last_login)))

    # Per-action counts in the window → fold into categories and verb buckets.
    act_rows = (await session.execute(
        select(AdminAuditLog.action, func.count())
        .where(AdminAuditLog.created_at >= start)
        .group_by(AdminAuditLog.action)
    )).all()
    by_category: dict[str, int] = {}
    buckets = {"create": 0, "update": 0, "delete": 0, "security": 0, "other": 0}
    _DESTRUCTIVE = ("delete", "clear", "cancel", "flush", "revoke", "refund",
                    "disable", "deactivate", "close", "purge", "remove")
    _CREATE = ("create", "make", "add", "upsert", "import")
    _UPDATE = ("update", "set", "edit", "toggle", "enable", "role", "settings",
               "interval", "image", "expiry")
    _SECURITY = ("admin.", "security", "login", "logout", "2fa", "password", "moderation")
    for act, n in act_rows:
        n = int(n)
        cat = act.split(".", 1)[0] if act else "other"
        by_category[cat] = by_category.get(cat, 0) + n
        verb = act.rsplit(".", 1)[-1] if act else ""
        if any(s in act for s in _SECURITY):
            buckets["security"] += n
        elif any(verb.startswith(d) or d in act for d in _DESTRUCTIVE):
            buckets["delete"] += n
        elif any(verb.startswith(c) for c in _CREATE):
            buckets["create"] += n
        elif any(verb.startswith(u) for u in _UPDATE):
            buckets["update"] += n
        else:
            buckets["other"] += n

    day_rows = (await session.execute(
        select(func.date(AdminAuditLog.created_at).label("d"), func.count())
        .where(AdminAuditLog.created_at >= start)
        .group_by("d").order_by("d")
    )).all()
    by_day = [{"date": str(d), "count": int(n)} for d, n in day_rows]

    top_rows = (await session.execute(
        select(AdminAuditLog.admin_id, func.count().label("c"),
               func.max(AdminAuditLog.created_at))
        .where(AdminAuditLog.created_at >= start)
        .group_by(AdminAuditLog.admin_id).order_by(func.count().desc()).limit(8)
    )).all()
    directory = await _admin_directory(session, {r[0] for r in top_rows})
    top_admins = [
        {"admin_id": aid, "email": directory.get(aid, (None, None))[0],
         "role": directory.get(aid, (None, None))[1], "count": int(c),
         "last_at": last.isoformat() if last else None}
        for aid, c, last in top_rows
    ]

    top_actions = sorted(
        ({"action": a, "count": int(n)} for a, n in act_rows),
        key=lambda x: x["count"], reverse=True,
    )[:12]

    return {
        "days": days,
        "total": total, "today": today, "last_hour": last_hour,
        "distinct_admins": distinct_admins, "admins_total": admins_total,
        "last_action_at": last_action_at.isoformat() if last_action_at else None,
        "last_login_at": last_login_at.isoformat() if last_login_at else None,
        "buckets": buckets,
        "by_category": [{"category": c, "count": n} for c, n in
                        sorted(by_category.items(), key=lambda x: x[1], reverse=True)],
        "by_day": by_day,
        "top_admins": top_admins,
        "top_actions": top_actions,
    }


_AUDIT_EXPORT_HEADER = [
    "id", "created_at", "action", "category", "admin_id", "admin_email",
    "admin_role", "target_type", "target_id", "ip", "before", "after",
]
_AUDIT_EXPORT_CAP = 200_000  # safety ceiling so a no-filter export can't exhaust memory


@router.get("/audit/export.csv")
async def export_audit_csv(
    request: Request,
    action: str | None = None,
    admin_id: int | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    q: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = _AUDIT_EXPORT_CAP,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
):
    """Full filtered audit export as CSV (server-side) — every matching row up to a
    safety cap, NOT just the page the UI loaded. Uses the same filters as GET /audit,
    enriches with admin email/role, and serializes before/after as JSON. The export
    action is itself audited. CSV cells are formula-injection-safe."""
    # Reuse the exports module's pure CSV helpers (formula-injection-safe + streaming).
    from api.admin.exports import _csv_response, _rows_to_csv

    limit = max(1, min(limit, _AUDIT_EXPORT_CAP))
    filters = _audit_filters(action, admin_id, target_type, target_id, q, since, until)
    rows = (await session.scalars(
        select(AdminAuditLog).where(*filters)
        .order_by(AdminAuditLog.id.desc()).limit(limit)
    )).all()
    directory = await _admin_directory(session, {a.admin_id for a in rows})
    out_rows = []
    for a in rows:
        email, role = directory.get(a.admin_id, (None, None))
        category = a.action.split(".", 1)[0] if a.action else ""
        out_rows.append([
            a.id, a.created_at.isoformat() if a.created_at else "", a.action, category,
            a.admin_id, email or "", role or "", a.target_type or "", a.target_id or "",
            a.ip or "",
            json.dumps(a.before, ensure_ascii=False) if a.before else "",
            json.dumps(a.after, ensure_ascii=False) if a.after else "",
        ])
    body = _rows_to_csv(_AUDIT_EXPORT_HEADER, out_rows)
    await audit(session, admin_id=admin.id, action="export.audit",
                target_type="export", target_id="audit.csv",
                after={"rows": len(out_rows)}, ip=_ip(request))
    return _csv_response("audit-export.csv", body)


# ---------- Promo codes ----------
class PromoCreate(BaseModel):
    # FIX: AUDIT13-M11 - bound promo fields. reward_amount was only floored at 0 with no
    # ceiling: for reward_type="premium" it is days (effectively infinite subscription),
    # for credits it minted an unbounded balance to every redeemer; code was unbounded.
    code: str = Field(..., max_length=64)
    reward_type: str = Field(..., max_length=16)   # credits | image | video | music | premium
    reward_amount: int = Field(0, ge=0, le=1_000_000)   # for premium: number of days
    max_uses: int = Field(1, ge=1, le=10_000_000)
    expires_at: str | None = None   # ISO datetime, or None for no expiry
    new_user_days: int = Field(0, ge=0, le=3650)    # > 0 = only accounts younger than N days may redeem


@router.get("/promos")
async def list_promos(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (await session.scalars(select(PromoCode).order_by(PromoCode.code))).all()
    return [
        {"code": p.code, "reward_type": p.reward_type, "reward_amount": p.reward_amount,
         "max_uses": p.max_uses, "used": p.used, "is_active": p.is_active,
         "new_user_days": p.new_user_days,
         "expires_at": p.expires_at.isoformat() if p.expires_at else None}
        for p in rows
    ]


@router.post("/promos")
async def create_promo(
    req: PromoCreate, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    code = req.code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="empty code")
    if req.reward_type not in ("credits", "image", "video", "music", "premium", "discount"):
        raise HTTPException(status_code=400, detail="bad reward_type")
    exp = None
    if req.expires_at:
        try:
            exp = datetime.fromisoformat(req.expires_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="bad expires_at (ISO)") from None
    if await session.get(PromoCode, code) is not None:
        raise HTTPException(status_code=409, detail="code already exists")
    session.add(PromoCode(
        code=code, reward_type=req.reward_type, reward_amount=max(0, req.reward_amount),
        max_uses=max(1, req.max_uses), expires_at=exp, is_active=True,
        new_user_days=max(0, req.new_user_days),
    ))
    # FIX: F20 - catch IntegrityError on commit: two concurrent create_promo requests
    # with the same code both pass the SELECT above (no FOR UPDATE), then the loser
    # trips the unique(code) constraint at commit. Without this catch it surfaces as a
    # raw 500; the caller should see a clean 409 "code already exists".
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="code already exists") from None
    await audit(session, admin_id=admin.id, action="promo.create", target_type="promo",
                target_id=code, after={"reward_type": req.reward_type, "amount": req.reward_amount},
                ip=_ip(request))
    return {"ok": True, "code": code}


@router.post("/promos/{code}/toggle")
async def toggle_promo(
    code: str, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    p = await session.get(PromoCode, code)
    if p is None:
        raise HTTPException(status_code=404, detail="not found")
    p.is_active = not p.is_active
    await audit(session, admin_id=admin.id, action="promo.toggle", target_type="promo",
                target_id=code, after={"is_active": p.is_active}, ip=_ip(request), commit=False)
    await session.commit()
    return {"code": code, "is_active": p.is_active}


class PromoExpiry(BaseModel):
    expires_at: str | None = None   # ISO datetime, or null to clear expiry


@router.put("/promos/{code}/expiry")
async def set_promo_expiry(
    code: str, req: PromoExpiry, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    p = await session.get(PromoCode, code)
    if p is None:
        raise HTTPException(status_code=404, detail="not found")
    exp = None
    if req.expires_at:
        try:
            exp = datetime.fromisoformat(req.expires_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="bad expires_at (ISO)") from None
    p.expires_at = exp
    await audit(session, admin_id=admin.id, action="promo.expiry", target_type="promo",
                target_id=code, after={"expires_at": req.expires_at}, ip=_ip(request), commit=False)
    await session.commit()
    return {"code": code, "expires_at": p.expires_at.isoformat() if p.expires_at else None}


@router.delete("/promos/{code}")
async def delete_promo(
    code: str, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    p = await session.get(PromoCode, code)
    if p is None:
        raise HTTPException(status_code=404, detail="not found")
    await session.delete(p)
    await audit(session, admin_id=admin.id, action="promo.delete", target_type="promo",
                target_id=code, ip=_ip(request), commit=False)
    await session.commit()
    return {"ok": True}


@router.get("/promos/bot-username")
async def promo_bot_username(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The default bot's @username (discovered via get_me on first connect), used to
    build share/redeem links `t.me/<username>?start=promo_<CODE>`. null until the bot
    has connected at least once."""
    username = await session.scalar(
        select(BotInstance.username)
        .where(BotInstance.username.isnot(None))
        .order_by(BotInstance.is_default.desc(), BotInstance.id.asc())
        .limit(1)
    )
    return {"username": username}


@router.get("/promos/{code}/redemptions")
async def promo_redemptions(
    code: str,
    limit: int = 200,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Who redeemed this promo, newest first. Sourced from the per-user redemption
    log (UsageLog action='promo_redeem', meta.code) — the same record the bot writes
    on a successful claim — so it's the authoritative activation history."""
    code = code.strip().upper()
    limit = max(1, min(limit, 500))
    rows = (await session.execute(
        select(UsageLog.user_id, UsageLog.created_at)
        .where(
            UsageLog.action == "promo_redeem",
            UsageLog.meta["code"].as_string() == code,
        )
        .order_by(UsageLog.created_at.desc())
        .limit(limit)
    )).all()
    return [
        {"user_id": uid, "redeemed_at": ts.isoformat() if ts else None}
        for uid, ts in rows
    ]


# ---------- Referral program ----------
async def _referral_stats(session: AsyncSession) -> dict:
    """Panel stats block. Shared by GET and PUT so both return the SAME shape — the
    frontend applies the PUT body directly, so a PUT missing `stats` white-screens
    the page on save (s.stats.top_referrers throws)."""
    total = (await session.scalar(select(func.count()).select_from(Referral))) or 0
    rewarded = (await session.scalar(
        select(func.count()).select_from(Referral).where(Referral.status == "rewarded")
    )) or 0
    top_rows = (await session.execute(
        select(Referral.referrer_id, func.count().label("n"))
        .group_by(Referral.referrer_id).order_by(func.count().desc()).limit(10)
    )).all()
    return {
        "total_referrals": total,
        "rewarded": rewarded,
        "top_referrers": [{"user_id": r[0], "count": r[1]} for r in top_rows],
    }


@router.get("/referrals/settings")
async def referral_settings(
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from core.services import pricing
    from core.services import referrals as ref_svc

    settings = await ref_svc.get_settings(session)
    fraud = await pricing.referral_fraud(session)
    return {
        **settings,
        # Account-age anti-fraud (merged in from the referral_fraud business_config
        # so the whole referral program is managed on ONE page).
        "age_fraud_enabled": bool(fraud["enabled"]),
        "min_referred_age_hours": int(fraud["min_referred_age_hours"]),
        "stats": await _referral_stats(session),
    }


class ReferralSettingsReq(BaseModel):
    enabled: bool | None = None
    reward_credits: int | None = None
    daily_invite_limit: int | None = None
    reward_on_register: bool | None = None
    require_subscription: bool | None = None
    invitee_reward_credits: int | None = None
    milestones: dict[str, int] | None = None
    age_fraud_enabled: bool | None = None
    min_referred_age_hours: int | None = None


@router.put("/referrals/settings")
async def set_referral_settings(
    req: ReferralSettingsReq, request: Request,
    admin: AdminUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from core.services import pricing
    from core.services import referrals as ref_svc

    changes: dict = {}
    if req.enabled is not None:
        changes["enabled"] = req.enabled
    if req.reward_credits is not None:
        changes["reward_credits"] = max(0, req.reward_credits)
    if req.daily_invite_limit is not None:
        changes["daily_invite_limit"] = max(0, req.daily_invite_limit)
    if req.reward_on_register is not None:
        changes["reward_on_register"] = req.reward_on_register
    if req.require_subscription is not None:
        changes["require_subscription"] = req.require_subscription
    if req.invitee_reward_credits is not None:
        changes["invitee_reward_credits"] = max(0, req.invitee_reward_credits)
    if req.milestones is not None:
        # Keep only positive count→bonus pairs (mirrors referrals._clean_milestones).
        changes["milestones"] = {
            str(int(k)): int(v) for k, v in req.milestones.items()
            if str(k).lstrip("-").isdigit() and int(k) > 0 and int(v) > 0
        }
    settings = await ref_svc.set_settings(session, **changes)

    # The account-age anti-fraud lives in the referral_fraud business_config; persist
    # it through the same save so the page is the single source for the whole program.
    fraud_patch: dict = {}
    if req.age_fraud_enabled is not None:
        fraud_patch["enabled"] = req.age_fraud_enabled
    if req.min_referred_age_hours is not None:
        fraud_patch["min_referred_age_hours"] = max(0, req.min_referred_age_hours)
    if fraud_patch:
        await pricing.set_config(session, {"referral_fraud": fraud_patch})
    fraud = await pricing.referral_fraud(session)

    await audit(session, admin_id=admin.id, action="referral.settings", target_type="setting",
                target_id="referral_settings", after={**changes, **fraud_patch}, ip=_ip(request))
    # Same shape as GET — the page applies this body directly; a missing `stats`
    # would crash the render on save.
    return {
        **settings,
        "age_fraud_enabled": bool(fraud["enabled"]),
        "min_referred_age_hours": int(fraud["min_referred_age_hours"]),
        "stats": await _referral_stats(session),
    }
