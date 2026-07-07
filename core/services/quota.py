"""Dual quota system (§10.1).

- text_req_week: chat + /s + image recognition + docs. Free = 100/week.
- premium users get a daily allowance (premium=100/day, premium_x2=200/day).
- mini_app_effects_week: independent Mini App photo-effect counter (free=25/week).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import TEXT_MODELS_BY_KEY
from core.models.user import User


@dataclass
class QuotaState:
    allowed: bool
    used: int
    limit: int
    is_premium: bool
    # When the base weekly/daily allowance is exhausted, a request is paid from the
    # user's ✨ balance (1 ✨ = 1 generation). ``credits_charged`` is how many ✨ this
    # consume spent (0 when it fit the base quota) so a later refund returns the
    # charge to the SAME budget. ``credits_balance`` is the ✨ left after the charge.
    credits_charged: int = 0
    credits_balance: int = 0


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    """Treat naive datetimes (e.g. from SQLite) as UTC so arithmetic is safe."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _maybe_reset_weekly(user: User) -> None:
    start = _aware(user.week_start)
    if start is None or _now() - start >= timedelta(days=7):
        user.text_req_week = 0
        user.week_start = _now()


def _maybe_reset_daily(user: User) -> None:
    start = _aware(user.day_start)
    if start is None or _now() - start >= timedelta(days=1):
        user.text_req_day = 0
        user.day_start = _now()


def _maybe_reset_miniapp(user: User) -> None:
    # premium resets daily (200/day), free resets weekly (25/week) — §10.1
    window = timedelta(days=1) if user.is_premium else timedelta(days=7)
    start = _aware(user.mini_app_week_start)
    if start is None or _now() - start >= window:
        user.mini_app_effects_week = 0
        user.mini_app_week_start = _now()


async def _limits(session: AsyncSession) -> dict[str, int]:
    """Effective limits, live-editable from the admin panel (falls back to the
    .env/code defaults when no override is set or the config table is absent)."""
    from core.services import pricing

    return await pricing.limits(session)


async def miniapp_limit(session: AsyncSession, user: User) -> int:
    lim = await _limits(session)
    if user.sub_tier == "premium_x2":
        return lim["premium_x2_daily"]
    return lim["premium_daily"] if user.is_premium else lim["free_miniapp_weekly"]


async def miniapp_quota_state(session: AsyncSession, user: User) -> QuotaState:
    _maybe_reset_miniapp(user)
    limit = await miniapp_limit(session, user)
    return QuotaState(
        user.mini_app_effects_week < limit,
        user.mini_app_effects_week,
        limit,
        user.is_premium,
    )


async def _vip_bonus(session: AsyncSession, user: User) -> tuple[int, int]:
    """(daily, weekly) extra allowance from the user's VIP tier — 0 when VIP is off."""
    from core.services import loyalty

    try:
        return await loyalty.vip_bonus(session, user)
    except Exception:  # noqa: BLE001 — VIP config/spend lookup must never block quota
        return 0, 0


async def daily_limit(session: AsyncSession, user: User) -> int:
    lim = await _limits(session)
    base = lim["premium_x2_daily"] if user.sub_tier == "premium_x2" else lim["premium_daily"]
    bonus_daily, _ = await _vip_bonus(session, user)
    return base + bonus_daily


async def text_quota_state(session: AsyncSession, user: User) -> QuotaState:
    """Read current text-quota state (does not persist resets)."""
    if user.is_premium:
        _maybe_reset_daily(user)
        limit = await daily_limit(session, user)
        return QuotaState(user.text_req_day < limit, user.text_req_day, limit, True)
    _maybe_reset_weekly(user)
    _, bonus_weekly = await _vip_bonus(session, user)
    limit = (await _limits(session))["free_text_weekly"] + bonus_weekly
    return QuotaState(user.text_req_week < limit, user.text_req_week, limit, False)


async def effective_text_cost(
    session: AsyncSession, model_key: str | None = None
) -> int:
    """Generations charged for one text request with `model_key`.

    Per-model cost comes from the DB catalog (admin-editable in AI-routing) when the
    model is registered there, else the static constants. In free-tier routing every
    model is served by one free model, so the cost is forced to 1 (no over-charging
    for a model the user doesn't actually receive)."""
    from core.ai_router.registry import routing_is_free_tier

    if routing_is_free_tier():
        return 1
    if model_key:
        try:
            from core.services.ai_routing import resolve_model

            m = await resolve_model(session, model_key)
        except Exception:  # noqa: BLE001 — ai_models table absent -> static fallback
            m = None
        if m is not None:
            return max(1, m.cost)
        if model_key in TEXT_MODELS_BY_KEY:
            return TEXT_MODELS_BY_KEY[model_key].cost
    return 1


async def consume_text(
    session: AsyncSession,
    user: User,
    model_key: str | None = None,
    *,
    cost: int | None = None,
    commit: bool = True,  # FIX: AUDIT-7 - allow caller to fold into single atomic tx
) -> QuotaState:
    """Charge a generation cost against the text quota, then the ✨ balance.

    Cost resolution order: explicit `cost` (e.g. documents = 3) → per-model cost
    from the catalog → 1. The base weekly/daily allowance is spent first; once it is
    exhausted the request is paid from the user's ✨ balance (earned from referrals /
    daily bonus / promos, or bought) at 1 ✨ per generation. Raises QuotaExceeded only
    when NEITHER the base allowance NOR the ✨ balance can cover the full cost.
    """
    if cost is None:
        cost = await effective_text_cost(session, model_key)

    # Lock this user's row so two concurrent generations can't both pass the
    # check-then-increment and overspend the quota (no-op on SQLite/tests).
    await session.refresh(user, with_for_update=True)

    if user.is_premium:
        _maybe_reset_daily(user)
        limit = await daily_limit(session, user)
        used_attr = "text_req_day"
        used = user.text_req_day
    else:
        _maybe_reset_weekly(user)
        _, bonus_weekly = await _vip_bonus(session, user)
        limit = (await _limits(session))["free_text_weekly"] + bonus_weekly
        used_attr = "text_req_week"
        used = user.text_req_week

    # Reject when the FULL cost won't fit, so a multi-credit request (docs=3, top
    # models) can't push a counter past its limit (was: used >= limit, which let one
    # over-limit generation through).
    if used + cost <= limit:
        # Base allowance covers it — charge the quota counter, ✨ untouched.
        setattr(user, used_attr, used + cost)
        if commit:  # FIX: AUDIT-7
            await session.commit()
        return QuotaState(True, used + cost, limit, user.is_premium,
                          credits_charged=0, credits_balance=user.credits)
    if user.credits >= cost:
        # Base allowance is spent — pay the whole request from the ✨ balance.
        user.credits -= cost
        if commit:  # FIX: AUDIT-7
            await session.commit()
        return QuotaState(True, limit, limit, user.is_premium,
                          credits_charged=cost, credits_balance=user.credits)
    # Neither the base allowance nor ✨ can cover the cost.
    if commit:  # FIX: AUDIT-7
        await session.commit()
    raise QuotaExceeded(QuotaState(False, used, limit, user.is_premium,
                                   credits_charged=0, credits_balance=user.credits))


async def try_consume_miniapp_free(
    session: AsyncSession, user: User, *, commit: bool = True
) -> bool:
    """Use one free Mini App effect slot. Returns False if the weekly/daily free
    allowance is exhausted (caller then charges image-pack credits / 🪙).

    ``commit=False`` keeps the slot increment (and its row lock) in the caller's
    open transaction so the consume commits together with the GenerationJob it pays
    for — a hard crash between the two can't burn a free slot with no job row."""
    await session.refresh(user, with_for_update=True)
    _maybe_reset_miniapp(user)
    if user.mini_app_effects_week >= await miniapp_limit(session, user):
        if commit:
            await session.commit()
        return False
    user.mini_app_effects_week += 1
    if commit:
        await session.commit()
    return True


async def refund_miniapp(session: AsyncSession, user: User) -> None:
    # Lock the row first (as consume does) so a refund racing a concurrent consume
    # can't lose that consume's increment via a stale read-modify-write.
    await session.refresh(user, with_for_update=True)
    user.mini_app_effects_week = max(0, user.mini_app_effects_week - 1)
    await session.commit()


def _maybe_reset_sponsored(user: User) -> None:
    start = _aware(user.sponsored_free_date)
    if start is None or start.date() != _now().date():
        user.sponsored_free_day = 0
        user.sponsored_free_date = _now()


async def try_consume_sponsored_free(
    session: AsyncSession, user: User, daily_limit: int, *, commit: bool = True
) -> bool:
    """Use one FREE sponsored-effect slot (the sponsor pays). Returns False when the
    per-UTC-day cap is reached or the cap is 0 (caller then charges normally).

    Same commit=False discipline as the free-slot consume: the increment stays in the
    caller's open transaction and commits with the GenerationJob it covers."""
    await session.refresh(user, with_for_update=True)
    _maybe_reset_sponsored(user)
    if daily_limit <= 0 or user.sponsored_free_day >= daily_limit:
        if commit:
            await session.commit()
        return False
    user.sponsored_free_day += 1
    if commit:
        await session.commit()
    return True


def sponsored_free_remaining(user: User, daily_limit: int) -> int:
    """How many free sponsored generations the user has left today — a pure read (no
    mutation), for honest price display before the charge happens."""
    start = _aware(user.sponsored_free_date)
    used = user.sponsored_free_day if (start and start.date() == _now().date()) else 0
    return max(0, daily_limit - used)


async def refund_sponsored(session: AsyncSession, user: User) -> None:
    # Lock first (mirrors refund_miniapp) so a refund racing a concurrent consume
    # can't lose that consume's increment.
    await session.refresh(user, with_for_update=True)
    user.sponsored_free_day = max(0, user.sponsored_free_day - 1)
    await session.commit()


async def refund_text(
    session: AsyncSession, user: User, cost: int = 1, *, credits_charged: int = 0,
    was_premium: bool | None = None,
) -> None:
    """Give back a previously-consumed text charge (provider failed).

    ``credits_charged`` (from the consume's QuotaState) is the part that was paid
    from the ✨ balance — it is returned to ✨; the remainder is returned to the
    weekly/daily counter. With the whole-to-one-budget consume rule this is either a
    pure ✨ refund or a pure quota refund, but the split form is kept correct too.

    ``was_premium`` (FIX: F13) — the user's premium status AT CHARGE TIME, not at
    refund time. consume_text charges by is_premium at charge time; if the user's
    subscription expires between charge and refund, reading user.is_premium now
    would decrement the WRONG counter (quota drift). Pass the consume's
    QuotaState.is_premium here so the refund lands in the same counter."""
    # Lock the row first (mirrors consume_text) to avoid a lost-update race where a
    # concurrent consume's increment is overwritten by this refund's stale read.
    await session.refresh(user, with_for_update=True)
    credits_charged = max(0, min(credits_charged, cost))
    if credits_charged:
        user.credits += credits_charged
    quota_part = cost - credits_charged
    if quota_part:
        # FIX: F13 - use the charge-time premium status (was_premium) when supplied;
        # fall back to current is_premium only when the caller didn't pass it.
        premium_at_charge = user.is_premium if was_premium is None else was_premium
        if premium_at_charge:
            user.text_req_day = max(0, user.text_req_day - quota_part)
        else:
            user.text_req_week = max(0, user.text_req_week - quota_part)
    await session.commit()


class QuotaExceeded(Exception):
    def __init__(self, state: QuotaState):
        self.state = state
        super().__init__("quota exceeded")
