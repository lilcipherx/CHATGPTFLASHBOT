"""Gift purchase + redemption (ТЗ §6) — direct service calls against SQLite.

Same harness as test_promo_bonuses: real DB, real billing. Importing the gift
model registers its table with Base.metadata so create_all builds it.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base, User
from core.models.gift import Gift  # noqa: F401 — registers the gifts table
from core.services import gifts, pricing
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


async def _user(session, uid: int) -> User:
    u, _ = await get_or_create_user(session, uid, username=f"u{uid}")
    return u


async def _make_sub_gift(session, buyer_id=1, tx="tx1") -> Gift:
    return await gifts.create_gift(
        session, buyer_id=buyer_id, kind="sub", product="premium",
        months=1, qty=None, gateway="stars", amount=600, gateway_tx_id=tx,
    )


async def test_create_gift_returns_code():
    async with SessionFactory() as s:
        gift = await _make_sub_gift(s)
        assert gift is not None
        # FIX: AUDIT-TEST - code is now an uppercased token_urlsafe(16) (~22 chars,
        # ~128 bits) — the old "<= 10" bound predated the entropy bump (AUDIT-174).
        assert gift.code and len(gift.code) >= 16 and gift.code == gift.code.upper()
        assert gift.status == "paid"


async def test_redeem_applies_premium():
    async with SessionFactory() as s:
        gift = await _make_sub_gift(s, buyer_id=1)
        code = gift.code
    async with SessionFactory() as s:
        friend = await _user(s, 2)
        ok, _msg = await gifts.redeem_gift(s, code, friend)
        assert ok is True
        await s.refresh(friend)
        assert friend.sub_tier == "premium"
        assert friend.sub_expires is not None
        assert friend.is_premium is True


async def test_redeem_twice_second_fails():
    async with SessionFactory() as s:
        gift = await _make_sub_gift(s, buyer_id=1)
        code = gift.code
    async with SessionFactory() as s:
        friend = await _user(s, 2)
        ok1, _ = await gifts.redeem_gift(s, code, friend)
        assert ok1 is True
    async with SessionFactory() as s:
        friend2 = await _user(s, 3)
        ok2, msg = await gifts.redeem_gift(s, code, friend2)
        assert ok2 is False
        assert "уже" in msg


async def test_rejected_second_redeemer_gets_no_entitlement():
    """The second redeemer of an already-used code must receive NOTHING — the gift
    grants the entitlement exactly once (the FOR UPDATE lock serializes concurrent
    redeems; the status guard + billing idempotency keep it single-grant)."""
    async with SessionFactory() as s:
        gift = await _make_sub_gift(s, buyer_id=1)
        code = gift.code
    async with SessionFactory() as s:
        first = await _user(s, 2)
        ok1, _ = await gifts.redeem_gift(s, code, first)
        assert ok1 is True
    async with SessionFactory() as s:
        second = await _user(s, 3)
        ok2, _ = await gifts.redeem_gift(s, code, second)
        assert ok2 is False
        await s.refresh(second)
        assert second.is_premium is False  # nothing leaked to the rejected redeemer
    async with SessionFactory() as s:
        from sqlalchemy import select as _select
        g = await s.scalar(_select(Gift).where(Gift.code == code))
        # redeemed_by stays the FIRST (winning) redeemer, not overwritten by the loser.
        assert g.redeemed_by == 2


async def test_redeem_unknown_code_fails():
    async with SessionFactory() as s:
        friend = await _user(s, 2)
        ok, msg = await gifts.redeem_gift(s, "NOPE123456", friend)
        assert ok is False
        assert "не найден" in msg


async def test_self_redeem_rejected():
    async with SessionFactory() as s:
        buyer = await _user(s, 1)
        gift = await _make_sub_gift(s, buyer_id=buyer.user_id)
        code = gift.code
    async with SessionFactory() as s:
        buyer = await _user(s, 1)
        ok, msg = await gifts.redeem_gift(s, code, buyer)
        assert ok is False
        assert "собственный" in msg


async def test_create_gift_idempotent_on_tx_id():
    async with SessionFactory() as s:
        g1 = await _make_sub_gift(s, tx="dup-tx")
        assert g1 is not None
        g2 = await _make_sub_gift(s, tx="dup-tx")
        assert g2 is None  # same charge id -> no second gift


async def test_parse_source_ignores_ref_and_redeem_payloads():
    from types import SimpleNamespace

    from bot.handlers.start import _parse_source

    def cmd(arg):
        return SimpleNamespace(args=arg)

    assert _parse_source(cmd("redeem_ABC123")) is None   # gift link, not a source
    assert _parse_source(cmd("ref_42")) is None          # referral, not a source
    assert _parse_source(cmd("src_promo")) == "promo"     # real source
    assert _parse_source(cmd("tiktok")) == "tiktok"


async def test_start_redeem_deeplink_redeems_gift():
    """The /start redeem_<code> deep-link (advertised in the gift-purchased message)
    must actually redeem the gift, not be treated as a traffic source."""
    from types import SimpleNamespace

    from bot.handlers.start import cmd_start

    async with SessionFactory() as s:
        gift = await _make_sub_gift(s, buyer_id=1)
        code = gift.code

    async with SessionFactory() as s:
        friend = await _user(s, 2)
        sent: list[str] = []

        async def _answer(text=None, **kw):
            sent.append(text)

        async def _noop(*a, **k):
            pass

        message = SimpleNamespace(answer=_answer, answer_photo=_noop, answer_video=_noop)
        command = SimpleNamespace(args=f"redeem_{code}")
        state = SimpleNamespace(set_state=_noop)

        await cmd_start(message, command, state, s, friend, True, lambda k, **kw: k)

        await s.refresh(friend)
        assert friend.is_premium is True          # gift applied via the deep-link
        assert friend.sub_tier == "premium"
        assert friend.source is None              # NOT recorded as a traffic source


async def test_redeem_pack_gift():
    async with SessionFactory() as s:
        gift = await gifts.create_gift(
            s, buyer_id=1, kind="pack", product="image_pack",
            months=None, qty=50, gateway="stars", amount=250, gateway_tx_id="pk1",
        )
        code = gift.code
    async with SessionFactory() as s:
        friend = await _user(s, 2)
        ok, _msg = await gifts.redeem_gift(s, code, friend)
        assert ok is True
        from core.models import PackBalance
        bal = await s.get(PackBalance, friend.user_id)
        assert bal.image_credits == 50
