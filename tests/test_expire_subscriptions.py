"""The hourly subscription-expiry sweep must NOT null the tier of an auto-renew
user still inside the renewal grace window — otherwise the daily auto-renewal sweep
(which requires sub_tier to be set) can never pick them up, and the documented grace
backstop is dead. Non-auto-renew users and grace-exhausted auto-renewers are cleared
immediately."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, User
from core.services.autorenew import RENEWAL_GRACE_HOURS
from workers.billing_tasks import _expire_subscriptions


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _seed(s, uid, *, hours_ago, auto_renew):
    s.add(User(
        user_id=uid, language_code="ru", sub_tier="premium",
        sub_expires=datetime.now(UTC) - timedelta(hours=hours_ago),
        auto_renew=auto_renew,
    ))


async def test_expire_respects_autorenew_grace():
    async with SessionFactory() as s:
        await _seed(s, 1, hours_ago=2, auto_renew=False)  # plain lapsed → clear
        await _seed(s, 2, hours_ago=2, auto_renew=True)  # auto-renew in grace → keep
        await _seed(s, 3, hours_ago=RENEWAL_GRACE_HOURS + 5, auto_renew=True)  # exhausted → clear
        await s.commit()

    await _expire_subscriptions(ctx=None)

    async with SessionFactory() as s:
        assert (await s.get(User, 1)).sub_tier is None       # cleared
        kept = await s.get(User, 2)
        assert kept.sub_tier == "premium"                    # preserved for the renewal sweep
        assert kept.sub_expires is not None
        assert (await s.get(User, 3)).sub_tier is None       # grace exhausted → cleared


async def test_future_subscription_untouched():
    async with SessionFactory() as s:
        s.add(User(
            user_id=9, language_code="ru", sub_tier="premium",
            sub_expires=datetime.now(UTC) + timedelta(days=5), auto_renew=False,
        ))
        await s.commit()
    await _expire_subscriptions(ctx=None)
    async with SessionFactory() as s:
        assert (await s.get(User, 9)).sub_tier == "premium"  # not yet expired
