"""Promo-code redemption — atomic and race-safe.

A single ``UPDATE promo_codes SET used = used + 1 WHERE used < max_uses ...``
claims one use slot. The row-level write lock that statement takes serialises
concurrent redemptions of the SAME code, and the reward grant + usage-log insert
run inside that same *uncommitted* transaction — so:

* the global ``max_uses`` limit can never be over-spent (the WHERE is the gate);
* a rejected redemption (expired / already-redeemed / unknown reward) rolls the
  claim back, so it never silently consumes a use;
* a single-use code can't be redeemed twice by the same user, because a
  concurrent redemption only proceeds after we commit and therefore sees the
  usage-log row written below.

This replaces the previous flow, where ``credits.grant`` / ``packs.refund``
committed internally and released the ``SELECT ... FOR UPDATE`` lock *before*
``used`` was incremented, letting two concurrent redemptions both pass the check.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import PromoCode, UsageLog, User
from core.services import credits, packs

_PACK_REWARDS = {"image", "video", "music"}
# Every reward a promo can grant. "premium" extends the subscription by
# reward_amount DAYS; "discount" is a checkout %-off (reward_amount = percent) that
# is APPLIED now and spent on the next purchase, not granted instantly; the rest are
# instant credit/pack grants.
REWARD_TYPES = {"credits", *_PACK_REWARDS, "premium", "discount"}
_MAX_DISCOUNT = 95  # never let a code drop a price below ~5% (mirrors the sale cap)

# Premium tiers ranked low→high so a promo's base "premium" grant never DOWNGRADES
# a user who already holds a higher active tier (it still extends their expiry).
_TIER_RANK = {None: 0, "": 0, "premium": 1, "premium_x2": 2}


@dataclass
class RedeemResult:
    ok: bool
    status: str          # "ok" | "invalid" | "already" | "not_eligible"
    reward_type: str = ""
    amount: int = 0


def _aware(dt: datetime | None) -> datetime | None:
    """Treat naive datetimes (SQLite) as UTC so expiry comparison never raises."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _grant_premium_days(user: User, days: int, now: datetime) -> None:
    """Extend ``user``'s Premium by ``days``, stacking onto an unexpired sub. Never
    downgrades an already-active higher tier (premium_x2), only extends its expiry."""
    current = _aware(user.sub_expires)
    active = current is not None and current > now
    base = current if active else now
    user.sub_expires = base + timedelta(days=days)
    if not active or _TIER_RANK.get(user.sub_tier, 0) < _TIER_RANK["premium"]:
        user.sub_tier = "premium"


async def _already_redeemed(session: AsyncSession, user_id: int, code: str) -> bool:
    # Push the code match into SQL (JSON ->> 'code') and stop at the first hit,
    # instead of loading every promo_redeem log for the user and scanning in
    # Python. `meta["code"].as_string()` renders portably (->>'code' on Postgres,
    # JSON_EXTRACT on SQLite); the (user_id) index narrows the scan.
    found = await session.scalar(
        select(UsageLog.id)
        .where(
            UsageLog.user_id == user_id,
            UsageLog.action == "promo_redeem",
            UsageLog.meta["code"].as_string() == code,
        )
        .limit(1)
    )
    return found is not None


async def redeem(session: AsyncSession, user: User, code: str) -> RedeemResult:
    """Redeem ``code`` for ``user``. Atomic: on any rejection the use slot is
    rolled back, so ``used`` only advances for a genuinely successful grant.

    The code is normalised (strip + upper-case) here — the single place every
    caller funnels through — so a user typing ``/promo welcome`` still matches a
    code the admin created as ``WELCOME`` (creation force-upper-cases it too, see
    api/admin/ops.create_promo). Without this, any promo containing letters is
    unredeemable unless the user reproduces the exact stored casing."""
    code = (code or "").strip().upper()
    if not code:
        return RedeemResult(False, "invalid")
    now = datetime.now(UTC)

    # Discount codes follow a different lifecycle: they are APPLIED to the account now
    # (no use slot consumed) and spent on the next successful purchase. Route them out
    # of the instant-grant claim flow below.
    peek = await session.scalar(select(PromoCode).where(PromoCode.code == code))
    if peek is not None and peek.reward_type == "discount":
        return await _apply_discount(session, user, peek, now)

    # Friendly fast-path: if THIS user already redeemed the code, say so directly
    # instead of letting them hit the generic "exhausted" path. This is a UX
    # short-circuit only — the authoritative per-user guard is the post-claim
    # re-check below, which also closes the concurrent same-user race.
    if await _already_redeemed(session, user.user_id, code):
        return RedeemResult(False, "already")

    # Atomically claim ONE use slot. WHERE enforces active + not-exhausted in a
    # single statement; the row-write lock serialises concurrent redemptions of
    # this code. Expiry is verified in Python below (tz-safe across SQLite/PG).
    claim = await session.execute(
        update(PromoCode)
        .where(
            PromoCode.code == code,
            PromoCode.is_active.is_(True),
            PromoCode.used < PromoCode.max_uses,
        )
        .values(used=PromoCode.used + 1)
    )
    if claim.rowcount == 0:
        # Unknown / inactive / exhausted — nothing claimed.
        await session.rollback()
        return RedeemResult(False, "invalid")

    promo = await session.scalar(select(PromoCode).where(PromoCode.code == code))
    if promo is None or (promo.expires_at and _aware(promo.expires_at) < now):
        await session.rollback()  # release the slot we just claimed
        return RedeemResult(False, "invalid")

    # Audience gate: a new-users-only code is rejected for accounts older than the
    # window (anti-abuse). created_at None / naive is treated as UTC (mirrors above).
    if promo.new_user_days and promo.new_user_days > 0:
        created = _aware(user.created_at)
        if created is None or now - created > timedelta(days=promo.new_user_days):
            await session.rollback()  # release the slot — not this user's campaign
            return RedeemResult(False, "not_eligible")

    if await _already_redeemed(session, user.user_id, code):
        await session.rollback()  # release the slot — this user already redeemed
        return RedeemResult(False, "already")

    amount = max(0, int(promo.reward_amount or 0))
    reward = promo.reward_type or ""
    # FIX: R11 - re-fetch the user row under FOR UPDATE so two concurrent promo
    # redemptions (or a redemption racing a payment) can't lose the grant via a
    # stale read of credits/sub_expires. The claim above already locks the PromoCode
    # row; this lock is on the User row that the grant mutates.
    await session.refresh(user, with_for_update=True)
    if reward == "credits":
        await credits.grant(session, user, amount, commit=False)
    elif reward in _PACK_REWARDS:
        await packs.refund(session, user.user_id, reward, amount, commit=False)
    elif reward == "premium":
        _grant_premium_days(user, amount, now)
    else:
        await session.rollback()  # misconfigured reward — don't consume the slot
        return RedeemResult(False, "invalid")

    session.add(UsageLog(
        user_id=user.user_id, action="promo_redeem",
        meta={"code": code, "reward_type": reward, "amount": amount},
    ))
    await session.commit()
    return RedeemResult(True, "ok", reward, amount)


def _discount_eligible(promo: PromoCode, user: User, now: datetime) -> str | None:
    """Validate a discount code for ``user`` WITHOUT consuming a slot. Returns a
    rejection status ("invalid"/"not_eligible") or None when it may be applied."""
    if (not promo.is_active or promo.used >= promo.max_uses
            or (promo.expires_at and _aware(promo.expires_at) < now)):
        return "invalid"
    if promo.new_user_days and promo.new_user_days > 0:
        created = _aware(user.created_at)
        if created is None or now - created > timedelta(days=promo.new_user_days):
            return "not_eligible"
    return None


async def _apply_discount(
    session: AsyncSession, user: User, promo: PromoCode, now: datetime
) -> RedeemResult:
    """Apply a discount code to the account (no slot consumed — that happens on the
    next paid purchase, via consume_discount). Idempotent per user: a code already
    spent by this user can't be re-applied."""
    bad = _discount_eligible(promo, user, now)
    if bad is not None:
        return RedeemResult(False, bad)
    if await _already_redeemed(session, user.user_id, promo.code):
        return RedeemResult(False, "already")
    user.discount_code = promo.code
    await session.commit()
    pct = max(0, min(_MAX_DISCOUNT, int(promo.reward_amount or 0)))
    return RedeemResult(True, "applied", "discount", pct)


async def active_discount(session: AsyncSession, user: User) -> int:
    """The percent off the user's currently-applied discount code grants right now
    (0 when none / invalid / expired / exhausted / ineligible / already spent). The
    code (not the percent) is stored on the user, so an admin deactivating or expiring
    it takes effect immediately."""
    code = (user.discount_code or "").strip().upper()
    if not code:
        return 0
    promo = await session.scalar(select(PromoCode).where(PromoCode.code == code))
    if promo is None or promo.reward_type != "discount":
        return 0
    if _discount_eligible(promo, user, datetime.now(UTC)) is not None:
        return 0
    if await _already_redeemed(session, user.user_id, code):
        return 0
    return max(0, min(_MAX_DISCOUNT, int(promo.reward_amount or 0)))


async def checkout_percent(session: AsyncSession, user: User) -> int:
    """The discount percent applied at checkout for ``user``: the larger of the global
    sale and the user's applied discount code (they do NOT stack — ТЗ §4)."""
    from core.services import pricing

    sale = await pricing.sale_percent(session)
    return max(sale, await active_discount(session, user))


async def consume_discount(session: AsyncSession, user: User, *, sale_pct: int) -> int:
    """Spend the user's applied discount code after a successful purchase — but only if
    it actually beat the sale (otherwise the sale already gave an equal/better price, so
    the code is kept for next time). Atomically claims a use slot + logs promo_redeem +
    clears the code. A code gone invalid is just cleared. Best-effort; returns the
    consumed percent or 0."""
    code = (user.discount_code or "").strip().upper()
    if not code:
        return 0
    pct = await active_discount(session, user)
    if pct <= 0:
        user.discount_code = None  # dead/spent code — clear it
        await session.commit()
        return 0
    if pct <= sale_pct:
        return 0  # the sale was at least as good — leave the code applied for later
    # FIX: AUDIT-LOW - serialize concurrent consume_discount for the SAME user so a
    # multi-use code (max_uses>1) can't be consumed more than once per user: two
    # concurrent purchases previously both passed the pre-claim eligibility read and
    # both claimed a slot. Lock the user row, then re-check per-user redemption before
    # claiming (mirrors the R11 lock + re-check in redeem()).
    await session.refresh(user, with_for_update=True)
    if await _already_redeemed(session, user.user_id, code):
        user.discount_code = None  # this user already spent it — clear & stop
        await session.commit()
        return 0
    claim = await session.execute(
        update(PromoCode)
        .where(
            PromoCode.code == code,
            PromoCode.is_active.is_(True),
            PromoCode.used < PromoCode.max_uses,
        )
        .values(used=PromoCode.used + 1)
    )
    # FIX: AUDIT-8 - only clear discount_code and return pct if claim succeeded
    if claim.rowcount:
        user.discount_code = None
        session.add(UsageLog(
            user_id=user.user_id, action="promo_redeem",
            meta={"code": code, "reward_type": "discount", "amount": pct},
        ))
        await session.commit()
        return pct
    # claim lost the race (max_uses exhausted) — do NOT clear discount_code
    await session.commit()
    return 0
