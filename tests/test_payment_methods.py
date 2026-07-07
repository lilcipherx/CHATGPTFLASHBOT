"""Saved payment-method store for auto-renewal (ТЗ §6).

Asserts save_method upserts one row per (user, gateway), re-saving replaces the
token in place, and get_method returns the active method (or None)."""
from __future__ import annotations

import pytest_asyncio
from sqlalchemy import func, select

from core.db import SessionFactory, engine
from core.models import Base, PaymentMethod
from core.payments.base import SavedMethod
from core.services import payment_methods


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_save_method_inserts_then_upserts():
    async with SessionFactory() as s:
        await payment_methods.save_method(
            s, user_id=1, gateway="yookassa",
            saved=SavedMethod(token="pm_1", last4="1111"),
        )
        # Re-saving the same (user, gateway) replaces the token in place, not a 2nd row.
        await payment_methods.save_method(
            s, user_id=1, gateway="yookassa",
            saved=SavedMethod(token="pm_2", last4="2222"),
        )

        count = await s.scalar(
            select(func.count()).select_from(PaymentMethod)
            .where(PaymentMethod.user_id == 1, PaymentMethod.gateway == "yookassa")
        )
        assert count == 1
        pm = await payment_methods.get_method(s, 1)
        assert pm is not None
        assert pm.token == "pm_2"
        assert pm.last4 == "2222"


async def test_get_method_none_when_unset_or_inactive():
    async with SessionFactory() as s:
        assert await payment_methods.get_method(s, 99) is None

        pm = await payment_methods.save_method(
            s, user_id=2, gateway="stripe",
            saved=SavedMethod(token="pm_s", customer_id="cus_2"),
        )
        assert await payment_methods.get_method(s, 2) is not None

        # Soft-disabling a method hides it from the renewal lookup.
        await payment_methods.deactivate(s, pm)
        assert await payment_methods.get_method(s, 2) is None


async def test_get_method_prefers_most_recent_across_gateways():
    async with SessionFactory() as s:
        await payment_methods.save_method(
            s, user_id=3, gateway="yookassa", saved=SavedMethod(token="pm_yk"),
        )
        await payment_methods.save_method(
            s, user_id=3, gateway="stripe",
            saved=SavedMethod(token="pm_stripe", customer_id="cus_3"),
        )
        pm = await payment_methods.get_method(s, 3)
        assert pm is not None
        # Two distinct gateways -> two rows; the latest save wins.
        assert pm.gateway == "stripe"
        assert pm.token == "pm_stripe"
