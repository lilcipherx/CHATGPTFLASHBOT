"""Admin user-management endpoints — input validation + object existence.

Calls the endpoint coroutines directly against a seeded SQLite schema (no HTTP),
mirroring tests/test_bots_admin.py. Covers two hardening fixes on api/admin/users:
  * grant_credits verifies the user exists for EVERY pack (not just 'credits'),
    so a pack grant for a missing user_id returns 404 instead of inserting a
    PackBalance row that violates the users FK / orphans.
  * grant_premium validates tier against the real tier set and bounds months.
"""
from __future__ import annotations

import types

import pytest
import pytest_asyncio
from fastapi import HTTPException

from api.admin.users import (
    CreditsRequest,
    PremiumRequest,
    grant_credits,
    grant_premium,
    list_user_countries,
    list_user_languages,
    search_users,
)
from core.db import SessionFactory, engine
from core.models import AdminUser, Base, PackBalance, User
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _req(ip: str = "10.0.0.1"):
    return types.SimpleNamespace(client=types.SimpleNamespace(host=ip))


async def _admin(role: str = "admin") -> AdminUser:
    async with SessionFactory() as s:
        a = AdminUser(email=f"{role}@x.io", password_hash="x", role=role)
        s.add(a)
        await s.commit()
        await s.refresh(a)
        return a


# ---- search_users: paged envelope + sorting --------------------------------
async def test_search_users_envelope_total_and_credit_sort():
    admin = await _admin()
    async with SessionFactory() as s:
        s.add_all([
            User(user_id=1, username="alice", credits=10),
            User(user_id=2, username="bob", credits=99),
            User(user_id=3, username="carol", credits=50),
        ])
        await s.commit()

        # Page envelope carries the total matching count (not just the page length).
        out = await search_users(limit=2, admin=admin, session=s)
        assert out["total"] == 3
        assert len(out["items"]) == 2
        assert out["sort"] == "created_desc"

        # Sort by credits desc → highest balance first.
        out = await search_users(sort="credits_desc", admin=admin, session=s)
        assert [u["user_id"] for u in out["items"]] == [2, 3, 1]

        # An unknown sort falls back to the default instead of erroring.
        out = await search_users(sort="bogus", admin=admin, session=s)
        assert out["sort"] == "created_desc"

        # total reflects the FILTERED set, not all rows.
        out = await search_users(q="bob", admin=admin, session=s)
        assert out["total"] == 1 and out["items"][0]["username"] == "bob"


async def test_user_countries_counts_desc_skips_empty():
    admin = await _admin()
    async with SessionFactory() as s:
        s.add_all([
            User(user_id=1, country="RU"), User(user_id=2, country="RU"),
            User(user_id=3, country="UZ"), User(user_id=4, country=None),
            User(user_id=5, country=""),
        ])
        await s.commit()
        out = await list_user_countries(admin=admin, session=s)
    # NULL/empty excluded; most-populous first.
    assert out == [{"code": "RU", "count": 2}, {"code": "UZ", "count": 1}]


async def test_user_languages_counts_desc():
    admin = await _admin()
    async with SessionFactory() as s:
        s.add_all([
            User(user_id=1, language_code="ru"), User(user_id=2, language_code="ru"),
            User(user_id=3, language_code="ru"), User(user_id=4, language_code="en"),
        ])
        await s.commit()
        out = await list_user_languages(admin=admin, session=s)
    # language_code is set for every user → reliable, ordered by count desc.
    assert out == [{"code": "ru", "count": 3}, {"code": "en", "count": 1}]


async def test_search_users_language_filter():
    admin = await _admin()
    async with SessionFactory() as s:
        s.add_all([
            User(user_id=1, language_code="ru"), User(user_id=2, language_code="en"),
        ])
        await s.commit()
        out = await search_users(language="en", admin=admin, session=s)
    assert out["total"] == 1 and out["items"][0]["user_id"] == 2


# ---- grant_credits: user existence for pack grants -------------------------
async def test_pack_grant_missing_user_404_no_orphan():
    admin = await _admin()
    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await grant_credits(
                user_id=424242, req=CreditsRequest(pack="image", amount=5),
                request=_req(), admin=admin, session=s,
            )
        assert ei.value.status_code == 404
    # No PackBalance orphan was created for the missing user.
    async with SessionFactory() as s:
        assert await s.get(PackBalance, 424242) is None


async def test_pack_grant_existing_user_credits_balance():
    admin = await _admin()
    async with SessionFactory() as s:
        await get_or_create_user(s, 5001)
        await s.commit()
    async with SessionFactory() as s:
        out = await grant_credits(
            user_id=5001, req=CreditsRequest(pack="image", amount=7),
            request=_req(), admin=admin, session=s,
        )
        assert out["ok"] is True
    async with SessionFactory() as s:
        bal = await s.get(PackBalance, 5001)
        assert bal is not None and bal.image_credits == 7


# ---- grant_premium: validation --------------------------------------------
async def test_grant_premium_bad_tier_rejected():
    admin = await _admin()
    async with SessionFactory() as s:
        await get_or_create_user(s, 5002)
        await s.commit()
    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await grant_premium(
                user_id=5002, req=PremiumRequest(months=1, tier="hacker"),
                request=_req(), admin=admin, session=s,
            )
        assert ei.value.status_code == 400


@pytest.mark.parametrize("months", [0, -3, 121, 100000])
async def test_grant_premium_months_out_of_range(months):
    admin = await _admin()
    async with SessionFactory() as s:
        await get_or_create_user(s, 5003)
        await s.commit()
    async with SessionFactory() as s:
        with pytest.raises(HTTPException) as ei:
            await grant_premium(
                user_id=5003, req=PremiumRequest(months=months, tier="premium"),
                request=_req(), admin=admin, session=s,
            )
        assert ei.value.status_code == 400


async def test_grant_premium_valid_sets_subscription():
    admin = await _admin()
    async with SessionFactory() as s:
        await get_or_create_user(s, 5004)
        await s.commit()
    async with SessionFactory() as s:
        out = await grant_premium(
            user_id=5004, req=PremiumRequest(months=3, tier="premium_x2"),
            request=_req(), admin=admin, session=s,
        )
        assert out["ok"] is True
    async with SessionFactory() as s:
        u = await s.get(User, 5004)
        assert u.sub_tier == "premium_x2" and u.is_premium is True
