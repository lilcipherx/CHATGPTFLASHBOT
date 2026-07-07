"""VIP / loyalty levels (ТЗ §4 monetization).

A user is auto-assigned the highest VIP tier whose ``min_spent`` threshold their
cumulative spend has reached. Spend is normalised to a Stars-equivalent so fiat and
Stars purchases count on one scale. Tiers grant extra daily/weekly generation
allowance (wired into core.services.quota). All config is live-editable via
business_config; disabled by default, so this is inert until an admin opts in.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models import Transaction, UsageLog, User
from core.services import pricing


async def total_spend_stars(session: AsyncSession, user_id: int) -> int:
    """Cumulative paid spend for a user, normalised to a Stars-equivalent integer.

    Stars purchases count directly; fiat purchases (minor units) are converted back
    via the same rates checkout uses (settings.stars_to_rub / stars_to_usd)."""
    rows = (await session.execute(
        select(Transaction.gateway, func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.user_id == user_id, Transaction.status == "paid")
        .group_by(Transaction.gateway)
    )).all()
    # FIX: AUDIT-129 - use Decimal for spend calculation (avoid float precision loss)
    from decimal import Decimal
    total = Decimal("0")
    for gateway, amount in rows:
        if not amount:
            continue
        if gateway == "stars":
            total += Decimal(str(amount))
        elif gateway in ("stripe", "crypto"):
            rate = settings.stars_to_usd
            total += Decimal(str(amount)) / (Decimal(str(rate)) * 100) if rate else Decimal("0")
        else:  # YooKassa / Tribute / other RUB gateways
            rate = settings.stars_to_rub
            total += Decimal(str(amount)) / (Decimal(str(rate)) * 100) if rate else Decimal("0")
    return int(total)


async def tier_for(session: AsyncSession, user: User) -> dict | None:
    """The user's current VIP tier (highest reached), or None when VIP is disabled
    or the user qualifies for no tier."""
    cfg = await pricing.vip_config(session)
    if not cfg["enabled"] or not cfg["tiers"]:
        return None
    spent = await total_spend_stars(session, user.user_id)
    reached = [t for t in cfg["tiers"] if spent >= t["min_spent"]]
    return reached[-1] if reached else None  # tiers are sorted ascending


async def vip_bonus(session: AsyncSession, user: User) -> tuple[int, int]:
    """(bonus_daily, bonus_weekly) extra generation allowance from the user's VIP
    tier. (0, 0) when VIP is off or no tier is reached."""
    tier = await tier_for(session, user)
    if tier is None:
        return 0, 0
    return tier["bonus_daily"], tier["bonus_weekly"]


async def progress(session: AsyncSession, user: User) -> dict | None:
    """The user's loyalty standing for display: ``{spent, current, next, to_next,
    tiers}`` (current/next are tier dicts or None). None when VIP is disabled or has
    no tiers. ``current`` is None when the spend hasn't reached the lowest tier yet;
    ``next`` is None when the top tier is reached."""
    cfg = await pricing.vip_config(session)
    if not cfg["enabled"] or not cfg["tiers"]:
        return None
    spent = await total_spend_stars(session, user.user_id)
    tiers = cfg["tiers"]  # sorted ascending by min_spent
    current = None
    nxt = None
    for t in tiers:
        if spent >= t["min_spent"]:
            current = t
        elif nxt is None:
            nxt = t
    return {
        "spent": spent,
        "current": current,
        "next": nxt,
        "to_next": max(0, nxt["min_spent"] - spent) if nxt else 0,
        "tiers": tiers,
    }


async def check_and_notify_upgrade(session: AsyncSession, user: User) -> dict | None:
    """After a purchase: if the user's spend has reached a VIP tier they were never
    congratulated for, DM them once and return that tier. Idempotent per (user, tier
    name) via a ``vip_tier_reached`` UsageLog row. Best-effort — never raises into the
    payment path (a VIP perk must never break a checkout)."""
    try:
        tier = await tier_for(session, user)
    except Exception:  # noqa: BLE001 — VIP lookup must never block a purchase
        return None
    if tier is None:
        return None
    # FIX: L5 - wrap the remaining DB ops in try/except to honor the docstring's
    # "never raises into the payment path" contract (was: only tier_for was wrapped).
    try:
        name = tier["name"]
        # Capture the int id + perks BEFORE the commit below expires the ORM object, so
        # the post-commit DM path never triggers lazy IO outside the greenlet.
        uid = user.user_id
        daily, weekly = tier["bonus_daily"], tier["bonus_weekly"]
        already = await session.scalar(
            select(UsageLog.id).where(
                UsageLog.user_id == uid,
                UsageLog.action == "vip_tier_reached",
                UsageLog.meta["tier"].as_string() == name,
            ).limit(1)
        )
        if already is not None:
            return None
        session.add(UsageLog(user_id=uid, action="vip_tier_reached", meta={"tier": name}))
        await session.commit()
    except Exception:  # noqa: BLE001 — FIX: L5 - never raise into payment path
        return None
    try:
        from core.bot_client import get_bot
        from core.i18n import t
        from core.services.users import user_locale

        locale = await user_locale(session, uid)
        await get_bot().send_message(
            uid, t("vip.reached", locale, tier=name, daily=daily, weekly=weekly),
        )
    except Exception:  # noqa: BLE001 — notification is best-effort
        pass
    return tier
