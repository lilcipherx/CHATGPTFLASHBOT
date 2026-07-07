"""Promo-code redemption against a real (SQLite) DB — proves the atomic claim
fixes the race where a single-use code could be redeemed more than max_uses times
and where one user could redeem the same code twice."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, PromoCode
from core.services import credits, promos
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def _make_promo(code: str, **kw) -> None:
    async with SessionFactory() as s:
        s.add(PromoCode(
            code=code,
            reward_type=kw.get("reward_type", "credits"),
            reward_amount=kw.get("reward_amount", 50),
            max_uses=kw.get("max_uses", 1),
            used=0,
            expires_at=kw.get("expires_at"),
            is_active=kw.get("is_active", True),
        ))
        await s.commit()


async def test_redeem_grants_credits_once():
    await _make_promo("WELCOME", reward_type="credits", reward_amount=50, max_uses=1)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 2001)
        res = await promos.redeem(s, user, "WELCOME")
        assert res.ok and res.status == "ok" and res.amount == 50
        assert user.credits == 50

    # same user can't redeem the same code again
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 2001)
        res2 = await promos.redeem(s, user, "WELCOME")
        assert res2.status == "already"
        assert user.credits == 50  # unchanged

    # and the single use slot is now exhausted for everyone else
    async with SessionFactory() as s:
        promo = await s.get(PromoCode, "WELCOME")
        assert promo.used == 1


async def _redeem_once(uid: int, code: str) -> str:
    # Fresh session + user per call, exactly like one /promo update in the bot.
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, uid)
        return (await promos.redeem(s, user, code)).status


async def test_unknown_and_expired_and_inactive_rejected():
    await _make_promo("EXPIRED", expires_at=datetime.now(UTC) - timedelta(days=1))
    await _make_promo("OFF", is_active=False)
    assert await _redeem_once(2002, "NOPE") == "invalid"
    assert await _redeem_once(2002, "EXPIRED") == "invalid"
    assert await _redeem_once(2002, "OFF") == "invalid"
    async with SessionFactory() as s:
        assert await credits.get_balance(s, 2002) == 0
        # a rejected redemption must NOT consume a use slot
        assert (await s.get(PromoCode, "EXPIRED")).used == 0
        assert (await s.get(PromoCode, "OFF")).used == 0


async def test_redeem_is_case_insensitive():
    # Admin stores codes upper-cased (api/admin/ops.create_promo force-uppers); the
    # bot must still match a user typing them in any case. redeem() normalises.
    await _make_promo("WELCOME", reward_type="credits", reward_amount=50, max_uses=1)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 2100)
        res = await promos.redeem(s, user, "  welcome ")  # lower + surrounding space
        assert res.ok and res.amount == 50
        assert user.credits == 50

    # a second redemption in yet another casing is still blocked for this user
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 2100)
        res2 = await promos.redeem(s, user, "Welcome")
        assert res2.status == "already"
    async with SessionFactory() as s:
        assert (await s.get(PromoCode, "WELCOME")).used == 1  # exactly one slot spent


async def test_concurrent_redeem_never_exceeds_max_uses():
    # 3 use slots, 10 distinct users racing → exactly 3 succeed, used == 3.
    await _make_promo("RACE", reward_type="credits", reward_amount=10, max_uses=3)

    async def _try(uid: int) -> str:
        async with SessionFactory() as s:
            user, _ = await get_or_create_user(s, uid)
            return (await promos.redeem(s, user, "RACE")).status

    results = await asyncio.gather(*(_try(3000 + i) for i in range(10)))
    assert results.count("ok") == 3
    async with SessionFactory() as s:
        assert (await s.get(PromoCode, "RACE")).used == 3


async def test_admin_promo_redemptions_history():
    """The admin redemptions endpoint lists WHO activated a code (from the per-user
    UsageLog the bot writes on each successful claim)."""
    from api.admin import ops
    from core.models import AdminUser

    await _make_promo("HISTORY", reward_type="credits", reward_amount=10, max_uses=5)
    async with SessionFactory() as s:
        u1, _ = await get_or_create_user(s, 5001)
        u2, _ = await get_or_create_user(s, 5002)
        await promos.redeem(s, u1, "HISTORY")
        await promos.redeem(s, u2, "HISTORY")
        admin = AdminUser(email="a@x.io", password_hash="x", role="admin", is_active=True)
        s.add(admin)
        await s.commit()
        out = await ops.promo_redemptions(code="history", admin=admin, session=s)
    assert {r["user_id"] for r in out} == {5001, 5002}
    assert all(r["redeemed_at"] for r in out)


async def test_start_promo_deeplink_redeems():
    """/start promo_<CODE> (the share/QR link) redeems the code and does NOT record
    the payload as a traffic source."""
    from types import SimpleNamespace

    from bot.handlers.start import cmd_start

    await _make_promo("LINKED", reward_type="credits", reward_amount=25, max_uses=3)
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 6001)

        async def _answer(text=None, **kw):
            pass

        async def _noop(*a, **k):
            pass

        message = SimpleNamespace(answer=_answer, answer_photo=_noop, answer_video=_noop)
        command = SimpleNamespace(args="promo_LINKED")
        state = SimpleNamespace(set_state=_noop)
        await cmd_start(message, command, state, s, user, True, lambda k, **kw: k)
        await s.refresh(user)
        assert user.credits == 25       # promo applied via the deep-link
        assert user.source is None      # NOT recorded as a traffic source


# ---- promo reward label localization (handlers.promo.reward_label) ----------
def test_reward_label_localizes_known_and_passes_unknown():
    from bot.handlers.promo import reward_label
    from core.i18n import Translator

    en, ru = Translator("en"), Translator("ru")
    assert reward_label(en, "credits") == "credits"
    assert reward_label(en, "image") == "image generations"
    assert reward_label(ru, "music") == "треков"
    # an unrecognised reward type is shown verbatim (no "promo.reward.x" leak)
    assert reward_label(en, "mystery") == "mystery"
