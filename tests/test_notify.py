"""Auto-notifications (ТЗ §7): selector correctness + run_notifications behaviour.

Users are seeded in a real SQLite DB (create_all fixture, same as test_promo_bonuses).
The Bot is monkeypatched to a fake that records sends, so no network is touched, and
Redis (fakeredis) is flushed between sub-tests so dedupe windows don't leak.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, User
from core.redis_client import redis_client
from core.services import notify, pricing


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await redis_client.flushall()
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield
    try:
        await pricing.redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


class _FakeBot:
    """Records (user_id, text) instead of hitting Telegram."""

    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, user_id, text, **kwargs):
        self.sent.append((user_id, text))


@pytest.fixture
def fake_bot(monkeypatch):
    bot = _FakeBot()
    monkeypatch.setattr("core.bot_client.get_bot", lambda: bot)
    return bot


def _now():
    return datetime.now(UTC)


async def _add(session, uid, **kw):
    user = User(user_id=uid, **kw)
    session.add(user)
    await session.flush()
    return user


# --------------------------------------------------------------------------- #
# selectors
# --------------------------------------------------------------------------- #
async def test_users_premium_expiring_selects_only_soon_to_expire():
    async with SessionFactory() as s:
        await _add(s, 1, sub_tier="premium", sub_expires=_now() + timedelta(days=2))
        await _add(s, 2, sub_tier="premium", sub_expires=_now() + timedelta(days=10))
        await _add(s, 3, sub_tier="premium", sub_expires=_now() - timedelta(days=1))
        await _add(s, 4)  # free user, no sub
        await s.commit()

        rows = await notify.users_premium_expiring(s, days_before=3)
        assert {u.user_id for u in rows} == {1}


async def test_users_low_balance_skips_zero_and_over_threshold():
    async with SessionFactory() as s:
        await _add(s, 1, credits=0)    # brand-new — skipped on purpose
        await _add(s, 2, credits=3)    # in range
        await _add(s, 3, credits=5)    # == threshold -> included
        await _add(s, 4, credits=20)   # over threshold
        await s.commit()

        rows = await notify.users_low_balance(s, threshold=5)
        assert {u.user_id for u in rows} == {2, 3}


async def test_users_inactive_selects_only_stale():
    async with SessionFactory() as s:
        await _add(s, 1, last_bonus_at=_now() - timedelta(days=30))
        await _add(s, 2, last_bonus_at=_now())
        await s.commit()
        # updated_at is set on commit (server_default/onupdate=now), so force the
        # stale user's activity timestamp into the past explicitly.
        u1 = await s.get(User, 1)
        old = _now() - timedelta(days=30)
        u1.updated_at = old
        u1.created_at = old
        await s.commit()

        rows = await notify.users_inactive(s, days=14)
        assert {u.user_id for u in rows} == {1}


async def test_users_bonus_available_selects_streak_at_risk():
    async with SessionFactory() as s:
        # claimed yesterday, not today -> streak at risk -> selected
        await _add(s, 1, last_bonus_at=_now() - timedelta(hours=20))
        # already claimed today -> excluded
        await _add(s, 2, last_bonus_at=_now() - timedelta(hours=1))
        # never claimed -> excluded (not nagged)
        await _add(s, 3)
        # streak already lapsed (3 days ago) -> excluded (win-back territory)
        await _add(s, 4, last_bonus_at=_now() - timedelta(days=3))
        # banned, claimed yesterday -> excluded
        await _add(s, 5, last_bonus_at=_now() - timedelta(hours=20), is_banned=True)
        await s.commit()
        # Relative offsets can cross the UTC day boundary just after midnight (e.g.
        # _now()-20h lands "today", _now()-1h lands "yesterday"); pin the two boundary
        # users to deterministic timestamps so the test is clock-stable all day.
        today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        u1 = await s.get(User, 1)
        u1.last_bonus_at = today - timedelta(hours=12)  # yesterday afternoon -> selected
        u2 = await s.get(User, 2)
        u2.last_bonus_at = today  # start of today -> "claimed today" -> excluded
        await s.commit()

        rows = await notify.users_bonus_available(s)
        assert {u.user_id for u in rows} == {1}


async def test_run_notifications_bonus_channel(fake_bot):
    async with SessionFactory() as s:
        await pricing.set_config(s, {"notifications": {
            "premium_expiry_enabled": False,
            "low_balance_enabled": False,
            "winback_enabled": False,
            "bonus_available_enabled": True,
        }})
    async with SessionFactory() as s:
        today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        await _add(s, 1, last_bonus_at=today - timedelta(hours=12))  # yesterday
        await _add(s, 2, last_bonus_at=_now())                       # today -> skip
        await s.commit()
        counts = await notify.run_notifications(s)

    assert counts["bonus_available"] == 1
    assert {uid for uid, _ in fake_bot.sent} == {1}


async def test_banned_users_are_never_selected():
    async with SessionFactory() as s:
        await _add(s, 1, credits=3, is_banned=True)
        await _add(
            s, 2, sub_tier="premium",
            sub_expires=_now() + timedelta(days=1), is_banned=True,
        )
        await s.commit()
        assert await notify.users_low_balance(s, threshold=5) == []
        assert await notify.users_premium_expiring(s, days_before=3) == []


# --------------------------------------------------------------------------- #
# run_notifications
# --------------------------------------------------------------------------- #
async def test_run_notifications_sends_enabled_channels(fake_bot):
    async with SessionFactory() as s:
        await pricing.set_config(s, {"notifications": {
            "premium_expiry_enabled": True, "premium_expiry_days_before": 3,
            "low_balance_enabled": True, "low_balance_threshold": 5,
            "winback_enabled": False,
        }})
    async with SessionFactory() as s:
        await _add(s, 1, sub_tier="premium", sub_expires=_now() + timedelta(days=1))
        await _add(s, 2, credits=2)
        await s.commit()
        counts = await notify.run_notifications(s)

    assert counts == {
        "premium_expiry": 1, "low_balance": 1, "winback": 0, "bonus_available": 0,
        "abandoned_cart": 0,
    }
    assert {uid for uid, _ in fake_bot.sent} == {1, 2}


async def test_disabled_channel_sends_nothing(fake_bot):
    async with SessionFactory() as s:
        await pricing.set_config(s, {"notifications": {
            "premium_expiry_enabled": False,
            "low_balance_enabled": False,
            "winback_enabled": False,
        }})
    async with SessionFactory() as s:
        await _add(s, 1, sub_tier="premium", sub_expires=_now() + timedelta(days=1))
        await _add(s, 2, credits=2)
        await s.commit()
        counts = await notify.run_notifications(s)

    assert counts == {
        "premium_expiry": 0, "low_balance": 0, "winback": 0, "bonus_available": 0,
        "abandoned_cart": 0,
    }
    assert fake_bot.sent == []


# --------------------------------------------------------------------------- #
# CTA buttons + personalized text
# --------------------------------------------------------------------------- #
async def test_notify_markup_targets_per_channel():
    from core.services.notify import _notify_markup

    def _cb(kind: str) -> str:
        return _notify_markup(kind, "ru").inline_keyboard[0][0].callback_data

    assert _cb("premium_expiry") == "premium:open"
    assert _cb("low_balance") == "premium:open"
    assert _cb("winback") == "premium:open"
    assert _cb("bonus_available") == "bonus:claim"


async def test_text_kwargs_personalizes_days_and_balance():
    from core.services.notify import _text_kwargs

    now = _now()
    u = User(user_id=9, sub_tier="premium",
             sub_expires=now + timedelta(days=2, hours=1), credits=4)
    assert _text_kwargs("premium_expiry", u, now) == {"days": 3}   # ceil(2d1h)
    assert _text_kwargs("low_balance", u, now) == {"balance": 4}
    assert _text_kwargs("winback", u, now) == {}


async def test_premium_expiry_message_is_personalized(fake_bot):
    async with SessionFactory() as s:
        await pricing.set_config(s, {"notifications": {
            "premium_expiry_enabled": True, "premium_expiry_days_before": 5,
            "low_balance_enabled": False, "winback_enabled": False,
        }})
    async with SessionFactory() as s:
        await _add(s, 1, sub_tier="premium", sub_expires=_now() + timedelta(days=2))
        await s.commit()
        await notify.run_notifications(s)
    text = fake_bot.sent[0][1]
    assert "{days}" not in text and "2" in text  # placeholder substituted with the days left


async def test_dedupe_no_resend_in_same_window(fake_bot):
    async with SessionFactory() as s:
        await pricing.set_config(s, {"notifications": {
            "premium_expiry_enabled": False,
            "low_balance_enabled": True, "low_balance_threshold": 5,
            "winback_enabled": False,
        }})
    async with SessionFactory() as s:
        await _add(s, 1, credits=2)
        await s.commit()

        first = await notify.run_notifications(s)
        second = await notify.run_notifications(s)

    assert first["low_balance"] == 1
    assert second["low_balance"] == 0  # deduped via redis
    assert len(fake_bot.sent) == 1
