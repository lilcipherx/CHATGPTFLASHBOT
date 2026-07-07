"""/invite (ТЗ §3): referral-count logic + branding default for welcome media.

The count helper and the pure ``invite_summary`` are tested directly against a real
SQLite DB (no live Bot needed). Branding is asserted empty by default (so /start
stays text-only) and reflects an admin override via pricing.set_config.
"""
from __future__ import annotations

import pytest_asyncio

from bot.handlers.invite import invite_summary
from core.db import SessionFactory, engine
from core.models import Base, User
from core.services import pricing, referrals
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        await pricing.redis_client.delete(pricing._CACHE_KEY)
    except Exception:  # noqa: BLE001
        pass
    yield
    try:
        await pricing.redis_client.connection_pool.disconnect()
    except Exception:  # noqa: BLE001
        pass


async def _seed_referrals(session, referrer_id: int, n: int, start: int = 100) -> None:
    """Create ``n`` users who carry ``referred_by == referrer_id`` + one unrelated."""
    for i in range(n):
        session.add(User(user_id=start + i, referred_by=referrer_id))
    session.add(User(user_id=start + 999, referred_by=referrer_id + 1))  # unrelated
    await session.commit()


async def test_count_referrals():
    async with SessionFactory() as s:
        referrer, _ = await get_or_create_user(s, 1, username="ref")
        await _seed_referrals(s, referrer.user_id, n=3)
        assert await referrals.count_referrals(s, referrer.user_id) == 3
        # a referrer with no invitees counts zero
        assert await referrals.count_referrals(s, 555) == 0


async def test_invite_summary():
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 42, username="u")
        await _seed_referrals(s, user.user_id, n=2)
        summary = await invite_summary(s, user)
        assert summary["link_suffix"] == "ref_42"  # link uses user_id
        assert summary["count"] == 2


async def test_branding_default_text_only():
    async with SessionFactory() as s:
        brand = await pricing.branding(s)
        # empty url by default -> /start stays text-only
        assert brand["start_media_url"] == ""
        assert brand["start_media_type"] == "photo"


async def test_branding_override():
    async with SessionFactory() as s:
        await pricing.set_config(
            s,
            {"branding": {"start_media_url": "https://x/y.mp4", "start_media_type": "video"}},
        )
    async with SessionFactory() as s:
        brand = await pricing.branding(s)
        assert brand["start_media_url"] == "https://x/y.mp4"
        assert brand["start_media_type"] == "video"
