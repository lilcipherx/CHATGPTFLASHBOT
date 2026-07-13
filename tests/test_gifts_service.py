"""Gift create + redeem (Loop coverage): idempotent minting on gateway_tx_id, and the
redeem decision matrix — unknown code, self-redeem, already-used, and a successful
credits redemption that flips the gift to 'redeemed'. Money-adjacent; DB only.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base
from core.services import gifts
from core.services.credits import get_balance
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_create_gift_is_idempotent_on_tx():
    async with SessionFactory() as s:
        g = await gifts.create_gift(
            s, buyer_id=5001, kind="credits", product="credits", months=None,
            qty=10, gateway="stars", amount=0, gateway_tx_id="ch_1",
        )
        assert g is not None and g.status == "paid" and len(g.code) > 0
        # A retry of the same charge must NOT mint a second gift.
        dup = await gifts.create_gift(
            s, buyer_id=5001, kind="credits", product="credits", months=None,
            qty=10, gateway="stars", amount=0, gateway_tx_id="ch_1",
        )
        assert dup is None


async def test_redeem_unknown_code_fails():
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 5100)
        ok, _msg = await gifts.redeem_gift(s, "NOSUCHCODE", user)
        assert ok is False


async def test_redeem_credits_success_then_already_used():
    async with SessionFactory() as s:
        g = await gifts.create_gift(
            s, buyer_id=5200, kind="credits", product="credits", months=None,
            qty=7, gateway="stars", amount=0, gateway_tx_id="ch_2",
        )
        recipient, _ = await get_or_create_user(s, 5201)
        ok, _msg = await gifts.redeem_gift(s, g.code, recipient)
        assert ok is True
        assert await get_balance(s, 5201) == 7
        # Re-redeeming the same code is refused (status flipped to 'redeemed').
        ok2, _msg2 = await gifts.redeem_gift(s, g.code, recipient)
        assert ok2 is False


async def test_redeem_sub_and_pack_kinds():
    async with SessionFactory() as s:
        gsub = await gifts.create_gift(
            s, buyer_id=5400, kind="sub", product="premium", months=1, qty=None,
            gateway="stars", amount=0, gateway_tx_id="gs1",
        )
        r1, _ = await get_or_create_user(s, 5401)
        ok, _msg = await gifts.redeem_gift(s, gsub.code, r1)
        assert ok is True
        await s.refresh(r1)
        assert r1.sub_expires is not None  # sub activated

        gpack = await gifts.create_gift(
            s, buyer_id=5400, kind="pack", product="image_pack", months=None, qty=5,
            gateway="stars", amount=0, gateway_tx_id="gp1",
        )
        r2, _ = await get_or_create_user(s, 5402)
        ok2, _msg2 = await gifts.redeem_gift(s, gpack.code, r2)
        assert ok2 is True


async def test_redeem_unknown_kind_and_billing_noop(monkeypatch):
    async with SessionFactory() as s:
        # unknown gift kind → the else branch rejects it
        bad = await gifts.create_gift(
            s, buyer_id=5500, kind="mystery", product="x", months=None, qty=1,
            gateway="stars", amount=0, gateway_tx_id="gu1",
        )
        u1, _ = await get_or_create_user(s, 5501)
        ok, _m = await gifts.redeem_gift(s, bad.code, u1)
        assert ok is False

        # each billing grant reporting a no-op (duplicate) → gift must NOT be marked
        # used (buyer keeps the code, recipient got nothing) — the not-ok branch per kind
        from core.services import billing

        async def _noop(*a, **k):
            return False
        monkeypatch.setattr(billing, "add_credits", _noop)
        monkeypatch.setattr(billing, "activate_subscription", _noop)
        monkeypatch.setattr(billing, "add_pack_credits", _noop)

        for i, (kind, product, qty, months) in enumerate([
            ("credits", "credits", 5, None),
            ("sub", "premium", None, 1),
            ("pack", "image_pack", 5, None),
        ]):
            g = await gifts.create_gift(
                s, buyer_id=5500, kind=kind, product=product, months=months, qty=qty,
                gateway="stars", amount=0, gateway_tx_id=f"gu-noop-{i}",
            )
            u, _ = await get_or_create_user(s, 5510 + i)
            ok_i, _mi = await gifts.redeem_gift(s, g.code, u)
            assert ok_i is False


async def test_redeem_own_gift_refused():
    async with SessionFactory() as s:
        buyer, _ = await get_or_create_user(s, 5300)
        g = await gifts.create_gift(
            s, buyer_id=5300, kind="credits", product="credits", months=None,
            qty=3, gateway="stars", amount=0, gateway_tx_id="ch_3",
        )
        ok, _msg = await gifts.redeem_gift(s, g.code, buyer)
        assert ok is False  # buyer == redeemer → self-redeem blocked
