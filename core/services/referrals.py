"""Referral rewards.

A user's `referred_by` is captured on /start (deep-link ref_<id>). The referrer is
rewarded ONCE, the first time the referred user makes a paid purchase. The
`referrals` table (referred_id is unique) is the idempotency guard, so retries /
multiple purchases never double-pay.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import REFERRAL_REWARD_CREDITS
from core.models import Pricing, Referral, UsageLog, User
from core.services import credits, pricing

# Admin-controlled referral program settings, stored in the `pricing` KV table
# under this key so they are runtime-editable from the admin panel (no redeploy).
SETTINGS_KEY = "referral_settings"
DEFAULT_SETTINGS: dict = {
    "enabled": True,
    "reward_credits": REFERRAL_REWARD_CREDITS,
    "daily_invite_limit": 0,   # 0 = unlimited invites attributed per day
    # True  → reward the referrer when the invited user REGISTERS (gated on the
    #         channel-subscription check below, as anti-fraud).
    # False → reward on the invited user's first PAID purchase (legacy behaviour).
    "reward_on_register": True,
    # When True (and a gate channel is configured), the registration reward is only
    # granted once the invited user is subscribed to the gate channel.
    "require_subscription": True,
    # Two-sided: ✨ granted to the INVITED user themselves on attribution (0 = off).
    "invitee_reward_credits": 0,
    # Milestone bonuses {"<invite count>": bonus ✨} — a one-time extra to the referrer
    # each time their invited-count crosses a threshold (gamification). {} = off.
    "milestones": {},
}


def _clean_milestones(raw) -> dict[int, int]:
    """Normalise the admin milestones map to ``{int count: int bonus}``, dropping any
    non-positive count/bonus. Tolerant of JSON string keys/values."""
    out: dict[int, int] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                count, bonus = int(k), int(v)
            except (TypeError, ValueError):
                continue
            if count > 0 and bonus > 0:
                out[count] = bonus
    return out


async def get_settings(session: AsyncSession) -> dict:
    row = await session.get(Pricing, SETTINGS_KEY)
    stored = (row.value or {}) if row else {}
    out = dict(DEFAULT_SETTINGS)
    out.update({k: stored[k] for k in DEFAULT_SETTINGS if k in stored})
    out["enabled"] = bool(out["enabled"])
    out["reward_credits"] = max(0, int(out["reward_credits"]))
    out["daily_invite_limit"] = max(0, int(out["daily_invite_limit"]))
    out["reward_on_register"] = bool(out["reward_on_register"])
    out["require_subscription"] = bool(out["require_subscription"])
    out["invitee_reward_credits"] = max(0, int(out["invitee_reward_credits"]))
    out["milestones"] = _clean_milestones(out["milestones"])
    return out


async def set_settings(session: AsyncSession, **changes) -> dict:
    row = await session.get(Pricing, SETTINGS_KEY)
    value = dict(row.value or {}) if row else {}
    for k in DEFAULT_SETTINGS:
        if k in changes and changes[k] is not None:
            value[k] = changes[k]
    if row is None:
        session.add(Pricing(key=SETTINGS_KEY, value=value))
    else:
        row.value = value
    await session.commit()
    return await get_settings(session)


async def count_referrals(session: AsyncSession, referrer_id: int) -> int:
    """How many users this referrer has invited (carry ``referred_by == id``)."""
    return (await session.scalar(
        select(func.count()).select_from(User).where(User.referred_by == referrer_id)
    )) or 0


async def can_attribute_invite(session: AsyncSession, referrer_id: int) -> bool:
    """Whether a new referred user may still be attributed to this referrer today,
    honouring the admin daily-invite limit (0 = unlimited). Counts users created
    today who already carry this referrer."""
    settings = await get_settings(session)
    if not settings["enabled"]:
        return False
    limit = settings["daily_invite_limit"]
    if limit <= 0:
        return True
    since = datetime.now(UTC) - timedelta(days=1)
    used = (await session.scalar(
        select(func.count()).select_from(User).where(
            User.referred_by == referrer_id, User.created_at >= since
        )
    )) or 0
    return used < limit


async def passes_fraud_check(session: AsyncSession, referred_user: User) -> bool:
    """Anti-fraud age gate (ТЗ §6): the referrer reward is withheld until the
    REFERRED account is old enough, combating instant fake-account farming.

    Reads the admin-controlled ``referral_fraud`` business_config. When disabled
    (default) returns True so reward logic is unchanged. When enabled, requires the
    referred account's age (now - created_at) >= min_referred_age_hours. A missing /
    naive created_at is treated as UTC (mirrors core.services.quota._aware)."""
    cfg = await pricing.referral_fraud(session)
    if not cfg["enabled"]:
        return True
    created = referred_user.created_at
    if created is None:
        return False  # no signup timestamp -> can't prove the account is old enough
    if created.tzinfo is None:  # SQLite returns naive datetimes
        created = created.replace(tzinfo=UTC)
    age = datetime.now(UTC) - created
    return age >= timedelta(hours=cfg["min_referred_age_hours"])


async def _grant_once(
    session: AsyncSession, user: User, status: str
) -> tuple[int, int] | None:
    """Insert the one-time Referral row (unique on referred_id) and credit the
    referrer. Returns ``(referrer_id, reward)`` or None if there is no referrer /
    already rewarded / referrer missing / program disabled. Idempotent."""
    referrer_id = user.referred_by
    if not referrer_id or referrer_id == user.user_id:
        return None
    settings = await get_settings(session)
    if not settings["enabled"]:
        return None
    reward = settings["reward_credits"]
    if await session.scalar(
        select(Referral.id).where(Referral.referred_id == user.user_id)
    ) is not None:
        return None
    referrer = await session.get(User, referrer_id)
    if referrer is None:
        return None
    session.add(
        Referral(
            referrer_id=referrer_id, referred_id=user.user_id,
            reward_type="credits", reward_amount=reward,
            status=status, rewarded_at=datetime.now(UTC),
        )
    )
    # FIX: AUDIT-133 - use SAVEPOINT so caller's session isn't poisoned
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        return None
    await credits.grant(session, referrer, reward)  # commits
    # A new invite was just rewarded → the referrer's count went up; grant + DM any
    # milestone bonus they've newly crossed (best-effort, never blocks the reward).
    await _grant_and_notify_milestones(session, referrer_id)
    return referrer_id, reward


async def _grant_and_notify_milestones(session: AsyncSession, referrer_id: int) -> None:
    """Grant the referrer a one-time bonus for each invite-count milestone they have
    reached but not yet been paid for (idempotent per (referrer, threshold) via a
    ``referral_milestone`` UsageLog row), and DM them about it best-effort."""
    settings = await get_settings(session)
    milestones = settings["milestones"]
    if not milestones:
        return
    count = await count_referrals(session, referrer_id)
    referrer = await session.get(User, referrer_id)
    if referrer is None:
        return
    # FIX: #6 - lock the referrer row BEFORE the milestone already-checks so two
    # concurrent referral grants to the same referrer can't both pass and double-grant
    # (was: no with_for_update, unlike R13 fix in grant_invitee_welcome).
    await session.refresh(referrer, with_for_update=True)
    granted: list[tuple[int, int]] = []
    for threshold in sorted(milestones):
        if count < threshold:
            break  # sorted ascending — nothing further reached
        already = await session.scalar(
            select(UsageLog.id).where(
                UsageLog.user_id == referrer_id,
                UsageLog.action == "referral_milestone",
                UsageLog.meta["threshold"].as_string() == str(threshold),
            ).limit(1)
        )
        if already is not None:
            continue
        bonus = milestones[threshold]
        await credits.grant(session, referrer, bonus, commit=False)
        # Store threshold as a STRING so the JSON ->> match above is type-stable
        # across SQLite/Postgres (mirrors promos._already_redeemed on meta.code).
        session.add(UsageLog(
            user_id=referrer_id, action="referral_milestone",
            meta={"threshold": str(threshold), "bonus": bonus},
        ))
        granted.append((threshold, bonus))
    if not granted:
        return
    await session.commit()
    # Best-effort DM, self-contained (own bot + locale); never disrupts the caller.
    try:
        from core.bot_client import get_bot
        from core.i18n import t
        from core.services.users import user_locale

        locale = await user_locale(session, referrer_id)
        bot = get_bot()
        for threshold, bonus in granted:
            await bot.send_message(
                referrer_id, t("ref.milestone", locale, count=threshold, amount=bonus)
            )
    except Exception:  # noqa: BLE001 — notification is best-effort
        pass


async def grant_invitee_welcome(session: AsyncSession, user: User) -> int:
    """Two-sided reward: grant the INVITED user their one-time welcome ✨ on
    attribution. Returns the amount granted (0 if disabled / already granted / no
    referrer). Idempotent via a ``referral_welcome`` UsageLog row for the invitee."""
    if not user.referred_by:
        return 0
    settings = await get_settings(session)
    if not settings["enabled"]:
        return 0
    amount = settings["invitee_reward_credits"]
    if amount <= 0:
        return 0
    # FIX: R13 - lock the user row BEFORE the already-granted check so two concurrent
    # /start ref_<id> requests for the same invited user (e.g. the bot + the Mini App
    # both registering at once) can't both pass the check and double-grant the welcome.
    # The unique on (user_id, action="referral_welcome") is the backstop, but the lock
    # makes the second caller see the just-inserted row and return 0 instead of
    # raising IntegrityError.
    await session.refresh(user, with_for_update=True)
    already = await session.scalar(
        select(UsageLog.id).where(
            UsageLog.user_id == user.user_id,
            UsageLog.action == "referral_welcome",
        ).limit(1)
    )
    if already is not None:
        return 0
    await credits.grant(session, user, amount, commit=False)
    session.add(UsageLog(user_id=user.user_id, action="referral_welcome", meta={"amount": amount}))
    await session.commit()
    return amount


async def total_earned(session: AsyncSession, referrer_id: int) -> int:
    """Total ✨ a referrer has earned: per-invite rewards (Referral rows) plus any
    milestone bonuses (referral_milestone UsageLog rows)."""
    per_invite = await session.scalar(
        select(func.coalesce(func.sum(Referral.reward_amount), 0))
        .where(Referral.referrer_id == referrer_id, Referral.reward_type == "credits")
    )
    milestone_rows = await session.scalars(
        select(UsageLog.meta).where(
            UsageLog.user_id == referrer_id, UsageLog.action == "referral_milestone"
        )
    )
    milestone_sum = sum(int((m or {}).get("bonus", 0)) for m in milestone_rows)
    return int(per_invite or 0) + milestone_sum


async def reward_referral_on_register(
    session: AsyncSession, bot, user: User
) -> tuple[int, int] | None:
    """Reward the referrer when the invited user REGISTERS (the default trigger).

    Anti-fraud: when ``require_subscription`` is on AND a gate channel is
    configured, the reward is withheld until the invited user is subscribed — so
    farming throwaway accounts that never subscribe earns nothing. Idempotent.
    Returns ``(referrer_id, reward)`` for an optional notification, else None."""
    settings = await get_settings(session)
    if not settings["enabled"] or not settings["reward_on_register"]:
        return None
    if not user.referred_by:
        return None
    if settings["require_subscription"]:
        from core.services import gate

        channels = await gate.active_channels(session)
        if channels and not await gate.is_subscribed(bot, user.user_id, session):
            return None  # not subscribed yet — retried when they pass the gate
    # NOTE: the referral_fraud AGE gate (passes_fraud_check) is intentionally NOT
    # applied here. The register reward fires the moment the invited user signs up,
    # when the account age is ~0, and the only retries (/start, gate:check) also
    # happen while the account is young — there is no after-aging retry, so applying
    # the age gate here would withhold the reward forever. Register-mode anti-fraud
    # is require_subscription + daily_invite_limit; the age gate guards the PAYMENT
    # trigger (reward_referral_on_payment), where the purchase naturally occurs after
    # the account has aged.
    return await _grant_once(session, user, status="registered")


async def reward_referral_on_payment(
    session: AsyncSession, user: User
) -> tuple[int, int] | None:
    """Grant the referrer a one-time 🪙 reward for `user`'s first payment.

    Only active when the program is NOT in register-reward mode (so a referral is
    rewarded exactly once, by exactly one trigger). Idempotent."""
    settings = await get_settings(session)
    if settings["reward_on_register"]:
        return None  # registration is the reward trigger; payment must not double-pay
    if not await passes_fraud_check(session, user):
        return None  # referred account too young — withhold the referrer payout
    return await _grant_once(session, user, status="rewarded")


async def notify_referrer(
    referrer_id: int | None,
    amount: int = REFERRAL_REWARD_CREDITS,
    *,
    reason: str = "register",
) -> None:
    """Best-effort DM to the referrer that they earned a reward. ``reason`` selects
    the wording so it matches the actual trigger ('register' = the invited user
    joined; 'purchase' = they made their first paid purchase).

    Self-contained: the locale read runs in its OWN short-lived session so a transient
    DB error can't poison the caller's (payment) transaction, and the whole body is
    wrapped in try/except so a notification failure never propagates into the flow that
    triggered it. The extra connection is negligible — this fires only on a referred
    user's first registration/purchase, not a hot path."""
    if not referrer_id:
        return
    from core.bot_client import get_bot
    from core.db import SessionFactory
    from core.i18n import t
    from core.services.users import user_locale

    try:
        async with SessionFactory() as session:
            locale = await user_locale(session, referrer_id)
        key = "ref.earned_purchase" if reason == "purchase" else "ref.earned_register"
        await get_bot().send_message(referrer_id, t(key, locale, amount=amount))
    except Exception:  # noqa: BLE001 — best-effort; never disrupt the caller's flow
        pass
