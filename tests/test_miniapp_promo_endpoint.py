"""Mini App /promo endpoint must never 500 on a rejected code.

Regression for the MissingGreenlet bug: promos.redeem() calls session.rollback()
on every rejection path (invalid / already / expired / misconfigured), which
EXPIRES the `user` ORM object. The endpoint then built its response with
``user.credits`` — a sync attribute read on an async session, which triggers a
lazy reload and raises sqlalchemy.exc.MissingGreenlet → HTTP 500 for ANY wrong
code typed in the Mini App. The bug is DB-agnostic (the greenlet error is in the
ORM async layer, not SQLite), so it would hit production Postgres too.

The fix captures the balance before redeem and returns the pre-redeem value on
any rejection (nothing changed), only reading the fresh user.credits on success.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, PromoCode, User


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _call(code: str, *, uid: int = 1):
    from api.routers.miniapp import PromoReq, redeem_promo

    async with SessionFactory() as s:
        return await redeem_promo(
            req=PromoReq(code=code),
            tg={"id": uid, "username": "u", "language_code": "ru"},
            session=s,
        )


async def _seed_user(uid: int = 1, credits: int = 100) -> None:
    async with SessionFactory() as s:
        s.add(User(user_id=uid, language_code="ru", credits=credits))
        await s.commit()


async def test_invalid_code_returns_200_not_500():
    # The original bug: an unknown code rolled back the session, then reading
    # user.credits raised MissingGreenlet. Must now return a clean ok=False.
    await _seed_user(credits=100)
    out = await _call("NO_SUCH_CODE")
    assert out["ok"] is False
    assert out["status"] == "invalid"
    assert out["amount"] == 0
    assert out["credits"] == 100  # unchanged, read safely after the rollback


async def test_already_redeemed_returns_200_not_500():
    await _seed_user(credits=100)
    async with SessionFactory() as s:
        s.add(PromoCode(code="WELCOME", reward_type="credits", reward_amount=25,
                        max_uses=10, used=0, is_active=True))
        await s.commit()
    first = await _call("WELCOME")
    assert first["ok"] is True and first["credits"] == 125
    # Second redemption rolls back (already) — must not 500, balance unchanged.
    second = await _call("welcome")  # lower-case proves normalisation too
    assert second["ok"] is False
    assert second["status"] == "already"
    assert second["credits"] == 125


async def test_valid_code_grants_and_reports_fresh_balance():
    await _seed_user(credits=50)
    async with SessionFactory() as s:
        s.add(PromoCode(code="BONUS", reward_type="credits", reward_amount=10,
                        max_uses=1, used=0, is_active=True))
        await s.commit()
    out = await _call("BONUS")
    assert out["ok"] is True
    assert out["amount"] == 10
    assert out["credits"] == 60
