"""Auto-engagement notifications (ТЗ §7): Premium-ending, low 🪙 balance, win-back,
daily-bonus-ready.

A single scheduler tick (workers.notify_tasks.send_notifications) calls
``run_notifications``, which reads the admin-tunable knobs from
``pricing.notifications`` and, per enabled channel, selects the matching users and
sends a short friendly nudge (localized to each user's language) via the
process-shared Bot.

Dedupe is Redis-only (no new table / migration): a ``notify:{kind}:{user_id}`` key
with a ~20h TTL means a user is nudged at most once per daily-ish window even if the
cron runs more often or the scheduler restarts.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog  # FIX: B8 - needed for log.warning in _dispatch/_dispatch_carts
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import SessionFactory
from core.models import User
from core.redis_client import first_seen
from core.services import pricing

log = structlog.get_logger()  # FIX: B8

# One nudge per ~daily window: the cron may tick more than once a day (or the beat
# process may restart), so a 20h TTL keeps re-sends out of the same day without
# blocking the next day's legitimate reminder.
_DEDUPE_TTL = 20 * 3600

# FIX: AUDIT12-M1 - keyset pagination batch size for the four user selectors.
# Bounded SELECT so a multi-million-row user table doesn't get loaded into a
# single server-side cursor / Python list in one shot (mirrors the broadcast_tasks
# pagination pattern). Each selector loops LIMIT/OFFSET until exhausted and
# accumulates into the returned list — the per-batch query is bounded while the
# final list is still O(matched users) (acceptable: Telegram send rate limits
# the dispatch, so memory churn stays bounded in practice).
_PAGE_LIMIT = 1000

def _activity_col():
    """Best-available last-activity timestamp for a User.

    There is no dedicated ``last_active`` column. ``updated_at`` (TimestampMixin,
    ``onupdate=func.now()``) bumps on any write to the user row — quota counters,
    settings changes, bonus claims — so it is the closest proxy for activity. We
    coalesce with ``last_bonus_at`` and ``created_at`` so a row that has never been
    updated since signup still has a sane timestamp. LIMITATION: a user who only
    reads (never triggers a row write) may look more inactive than they are.
    """
    return func.coalesce(User.updated_at, User.last_bonus_at, User.created_at)


async def users_premium_expiring(session: AsyncSession, days_before: int) -> list[User]:
    """Premium users whose sub_expires falls within ``days_before`` days from now and
    has not already passed (so we warn before, not after, expiry)."""
    # FIX: AUDIT12-M1 - keyset paginated SELECT (limit + offset loop).
    now = datetime.now(UTC)
    cutoff = now + timedelta(days=max(0, days_before))
    out: list[User] = []
    offset = 0
    while True:
        rows = await session.scalars(
            select(User).where(
                User.is_banned.is_(False),
                User.sub_tier.is_not(None),
                User.sub_expires.is_not(None),
                User.sub_expires > now,
                User.sub_expires <= cutoff,
            ).order_by(User.user_id).limit(_PAGE_LIMIT).offset(offset)
        )
        batch = rows.all()
        if not batch:
            break
        out.extend(batch)
        offset += _PAGE_LIMIT
    return out


async def users_low_balance(session: AsyncSession, threshold: int) -> list[User]:
    """Users with ``0 < credits <= threshold``.

    Zero is intentionally skipped: a brand-new user starts at 0 🪙 and has not yet
    engaged with the paid economy, so nagging them on day one is counter-productive.
    Once they spend down to a low-but-nonzero balance they are a real top-up target.
    """
    # FIX: AUDIT12-M1 - keyset paginated SELECT (limit + offset loop).
    out: list[User] = []
    offset = 0
    while True:
        rows = await session.scalars(
            select(User).where(
                User.is_banned.is_(False),
                User.credits > 0,
                User.credits <= threshold,
            ).order_by(User.user_id).limit(_PAGE_LIMIT).offset(offset)
        )
        batch = rows.all()
        if not batch:
            break
        out.extend(batch)
        offset += _PAGE_LIMIT
    return out


async def users_inactive(session: AsyncSession, days: int) -> list[User]:
    """Users whose best-available activity timestamp is older than ``days``."""
    # FIX: AUDIT12-M1 - keyset paginated SELECT (limit + offset loop).
    cutoff = datetime.now(UTC) - timedelta(days=max(0, days))
    activity = _activity_col()
    out: list[User] = []
    offset = 0
    while True:
        rows = await session.scalars(
            select(User).where(
                User.is_banned.is_(False),
                or_(activity < cutoff, activity.is_(None)),
            ).order_by(User.user_id).limit(_PAGE_LIMIT).offset(offset)
        )
        batch = rows.all()
        if not batch:
            break
        out.extend(batch)
        offset += _PAGE_LIMIT
    return out


async def users_bonus_available(session: AsyncSession) -> list[User]:
    """Users with a live daily-bonus streak at risk: they claimed YESTERDAY (UTC) but
    not yet today, so claiming today keeps the streak alive.

    Targets engaged bonus users only — someone who never claimed (``last_bonus_at``
    NULL) is never nagged, someone who already claimed today is excluded, and someone
    whose streak already lapsed (last claim older than yesterday) is left to win-back.
    """
    # FIX: AUDIT12-M1 - keyset paginated SELECT (limit + offset loop).
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    out: list[User] = []
    offset = 0
    while True:
        rows = await session.scalars(
            select(User).where(
                User.is_banned.is_(False),
                User.last_bonus_at.is_not(None),
                User.last_bonus_at >= yesterday,
                User.last_bonus_at < today,
            ).order_by(User.user_id).limit(_PAGE_LIMIT).offset(offset)
        )
        batch = rows.all()
        if not batch:
            break
        out.extend(batch)
        offset += _PAGE_LIMIT
    return out


# Per-channel CTA: the inline button under each nudge (label i18n key, callback). The
# callbacks are existing in-bot handlers — premium:open (the /premium menu) and
# bonus:claim (the daily-bonus grant). Winback upsells into the Premium menu too.
_NOTIFY_CTA = {
    "premium_expiry": ("notify.btn.renew", "premium:open"),
    "low_balance": ("notify.btn.topup", "premium:open"),
    "winback": ("notify.btn.open", "premium:open"),
    "bonus_available": ("notify.btn.bonus", "bonus:claim"),
}


def _notify_markup(kind: str, locale: str):
    """The inline CTA keyboard for a nudge (one button into the relevant in-bot flow),
    or None for a channel without a CTA."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from core.i18n import t

    cta = _NOTIFY_CTA.get(kind)
    if cta is None:
        return None
    label_key, callback = cta
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(label_key, locale), callback_data=callback)
    ]])


def _text_kwargs(kind: str, user: User, now: datetime) -> dict[str, Any]:
    """Per-channel placeholders for the nudge text: ``days`` left for premium_expiry,
    ``balance`` for low_balance. Other channels take no placeholders."""
    if kind == "premium_expiry":
        exp = user.sub_expires
        if exp is not None and exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        days = max(1, math.ceil((exp - now).total_seconds() / 86400)) if exp else 1
        return {"days": days}
    if kind == "low_balance":
        return {"balance": user.credits}
    return {}


async def _dispatch(kind: str, users: list[User], now: datetime) -> int:
    """Send ``kind`` to each user (best-effort, deduped). Returns the count sent. Each
    message is personalized (``_text_kwargs``) and carries a CTA button (``_notify_markup``).

    ``first_seen`` atomically claims the per-user dedupe key (``notify:{kind}:{uid}``,
    ~20h TTL) before the send, so two overlapping scheduler ticks can't both nudge the
    same user. Trade-off vs the old mark-after-send: a transient send failure isn't
    retried within the window — acceptable for best-effort engagement nudges."""
    from core.bot_client import get_bot
    from core.i18n import t

    bot = get_bot()
    sent = 0
    for user in users:
        if not await first_seen(f"notify:{kind}:{user.user_id}", _DEDUPE_TTL):
            continue
        try:
            locale = user.language_code or "ru"
            text = t(f"notify.{kind}", locale, **_text_kwargs(kind, user, now))
            await bot.send_message(user.user_id, text, reply_markup=_notify_markup(kind, locale))
        except Exception as exc:  # noqa: BLE001 — FIX: L7 - log so failures are observable
            log.warning("notify.dispatch_failed", kind=kind, user_id=user.user_id, error=str(exc))
            continue
        sent += 1
    return sent


async def _dispatch_carts(session: AsyncSession, intents: list) -> int:
    """Abandoned-cart nudges (ТЗ §7): one message per open cart, carrying a button that
    re-opens that product's menu (``intent.resume_cb``). ``reminded_at`` is claimed
    BEFORE the send so a crash/overlap can't double-nudge the same cart; trade-off is a
    transient send failure isn't retried (acceptable for best-effort engagement)."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from core.bot_client import get_bot
    from core.i18n import t
    from core.services.users import user_locale

    bot = get_bot()
    sent = 0
    for intent in intents:
        intent.reminded_at = datetime.now(UTC)
        await session.commit()  # claim first (one-shot guard)
        try:
            locale = await user_locale(session, intent.user_id)
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=t("notify.btn.cart", locale),
                                     callback_data=intent.resume_cb)
            ]])
            await bot.send_message(intent.user_id, t("notify.abandoned_cart", locale),
                                   reply_markup=kb)
        except Exception as exc:  # noqa: BLE001 — FIX: B9 - fixed: kind/user vars were wrong
            log.warning("notify.dispatch_failed", kind="abandoned_cart",
                        user_id=intent.user_id, error=str(exc))
            continue
        sent += 1
    return sent


async def run_notifications(session: AsyncSession | None = None) -> dict[str, int]:
    """Send all enabled engagement nudges; returns per-channel sent counts.

    Reads the live admin config (``pricing.notifications``); a disabled channel is
    skipped entirely (no select, no send). Each send is deduped via Redis and is
    best-effort per user (a failed send never aborts the run)."""
    if session is None:
        async with SessionFactory() as own:
            return await run_notifications(own)

    cfg = await pricing.notifications(session)
    now = datetime.now(UTC)
    counts = {"premium_expiry": 0, "low_balance": 0, "winback": 0,
              "bonus_available": 0, "abandoned_cart": 0}

    if cfg.get("premium_expiry_enabled"):
        users = await users_premium_expiring(session, cfg["premium_expiry_days_before"])
        counts["premium_expiry"] = await _dispatch("premium_expiry", users, now)

    if cfg.get("low_balance_enabled"):
        users = await users_low_balance(session, cfg["low_balance_threshold"])
        counts["low_balance"] = await _dispatch("low_balance", users, now)

    if cfg.get("winback_enabled"):
        users = await users_inactive(session, cfg["winback_inactive_days"])
        counts["winback"] = await _dispatch("winback", users, now)

    if cfg.get("bonus_available_enabled"):
        users = await users_bonus_available(session)
        counts["bonus_available"] = await _dispatch("bonus_available", users, now)

    if cfg.get("abandoned_cart_enabled"):
        from core.services import checkout

        intents = await checkout.abandoned(session, cfg["abandoned_cart_after_hours"])
        counts["abandoned_cart"] = await _dispatch_carts(session, intents)

    return counts
