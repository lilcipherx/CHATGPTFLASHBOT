"""End-to-end integration against a REAL (SQLite) database — exercises the
user/quota/pack-ledger/billing/mini-app services that pure unit tests couldn't
cover. Proves the money + quota logic works against a live DB engine."""
from __future__ import annotations

import pytest
import pytest_asyncio

from core.db import SessionFactory, engine
from core.models import Base
from core.services import billing, packs
from core.services.quota import QuotaExceeded, consume_text, try_consume_miniapp_free
from core.services.users import get_or_create_user


@pytest_asyncio.fixture(autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_user_upsert_and_balance_created():
    async with SessionFactory() as s:
        user, created = await get_or_create_user(s, 1001, username="alice")
        assert created is True
        again, created2 = await get_or_create_user(s, 1001, username="alice")
        assert created2 is False
        bal = await packs.get_balance(s, 1001, "image")
        assert bal == 0


async def test_text_quota_exhaustion():
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 1002)
        # free weekly limit is 100; consume 100 then expect QuotaExceeded
        for _ in range(100):
            await consume_text(s, user)
        with pytest.raises(QuotaExceeded):
            await consume_text(s, user)


async def test_atomic_pack_ledger():
    async with SessionFactory() as s:
        await get_or_create_user(s, 1003)
        await packs.refund(s, 1003, "image", 5)          # grant 5
        assert await packs.get_balance(s, 1003, "image") == 5
        assert await packs.try_consume(s, 1003, "image", 3) is True
        assert await packs.get_balance(s, 1003, "image") == 2
        # over-spend rejected, balance unchanged
        assert await packs.try_consume(s, 1003, "image", 5) is False
        assert await packs.get_balance(s, 1003, "image") == 2


async def test_pack_consume_commit_false_is_atomic_with_caller():
    # commit=False keeps the deduction in the caller's transaction so a generation
    # handler can commit it together with the GenerationJob (a crash before that
    # commit rolls the charge back — never a burned credit with no job).
    async with SessionFactory() as s:
        await get_or_create_user(s, 1099)
        await packs.refund(s, 1099, "image", 5)          # grant 5

    # consume(commit=False) then ROLL BACK = the "crash before job commit" case.
    async with SessionFactory() as s:
        assert await packs.try_consume(s, 1099, "image", 3, commit=False) is True
        await s.rollback()
    async with SessionFactory() as s:
        assert await packs.get_balance(s, 1099, "image") == 5   # deduction undone

    # consume(commit=False) then COMMIT = the success path (charge + job land together).
    async with SessionFactory() as s:
        assert await packs.try_consume(s, 1099, "image", 3, commit=False) is True
        await s.commit()
    async with SessionFactory() as s:
        assert await packs.get_balance(s, 1099, "image") == 2


async def test_text_quota_rejects_unaffordable_multicredit_cost():
    # A cost>1 request must not be allowed to push the counter past the limit (L7):
    # at 98/100 a 3-credit doc is rejected; at 97/100 it exactly fills to 100.
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 1010)
        for _ in range(97):
            await consume_text(s, user)  # cost 1 each → 97
        await consume_text(s, user, cost=3)  # 97 + 3 = 100, fits
        assert user.text_req_week == 100
    async with SessionFactory() as s:
        user2, _ = await get_or_create_user(s, 1011)
        for _ in range(98):
            await consume_text(s, user2)  # → 98
        with pytest.raises(QuotaExceeded):
            await consume_text(s, user2, cost=3)  # 98 + 3 = 101 > 100 → rejected
        assert user2.text_req_week == 98  # counter untouched on rejection


async def test_subscription_activation_idempotent():
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 1004)
        ok = await billing.activate_subscription(
            s, user, product="premium", months=3, gateway="stars",
            amount=1200, gateway_tx_id="charge_abc",
        )
        assert ok is True and user.is_premium is True
        # replaying the same gateway tx is a no-op (idempotency)
        again = await billing.activate_subscription(
            s, user, product="premium", months=3, gateway="stars",
            amount=1200, gateway_tx_id="charge_abc",
        )
        assert again is False


async def test_add_pack_credits_and_miniapp_quota():
    async with SessionFactory() as s:
        user, _ = await get_or_create_user(s, 1005)
        ok = await billing.add_pack_credits(
            s, user, pack="image_pack", qty=100, gateway="stars",
            amount=450, gateway_tx_id="pack_xyz",
        )
        assert ok is True
        assert await packs.get_balance(s, 1005, "image") == 100
        # free mini-app slot consumes the weekly counter, not credits
        assert await try_consume_miniapp_free(s, user) is True
        assert user.mini_app_effects_week == 1


async def test_refund_job_reverses_each_charge_type():
    # The canonical worker refund path (L5): 💎 / pack credit / free weekly slot.
    from core.models import GenerationJob, User
    from core.services.refunds import refund_job

    async with SessionFactory() as s:
        await get_or_create_user(s, 1020)

        job_d = GenerationJob(user_id=1020, service="x", pack_type="credits",
                              cost_credits=5, params={}, status="failed")
        s.add(job_d)
        await s.commit()
        await refund_job(s, job_d)
        assert (await s.get(User, 1020)).credits == 5

        job_p = GenerationJob(user_id=1020, service="x", pack_type="video",
                              cost_credits=2, params={}, status="failed")
        s.add(job_p)
        await s.commit()
        await refund_job(s, job_p)
        assert await packs.get_balance(s, 1020, "video") == 2

        u = await s.get(User, 1020)
        u.mini_app_effects_week = 3
        await s.commit()
        job_f = GenerationJob(user_id=1020, service="x", pack_type=None,
                              cost_credits=0, params={"free": True}, status="failed")
        s.add(job_f)
        await s.commit()
        await refund_job(s, job_f)
        assert (await s.get(User, 1020)).mini_app_effects_week == 2


class _FakeBot:
    """Records the Stars money refunds issued; send_message is a no-op."""
    def __init__(self, fail: bool = False):
        self.refunded: list[tuple[int, str]] = []
        self._fail = fail

    async def refund_star_payment(self, *, user_id, telegram_payment_charge_id):
        if self._fail:
            raise RuntimeError("telegram refund failed")
        self.refunded.append((user_id, telegram_payment_charge_id))

    async def send_message(self, *a, **k):
        pass


async def test_refund_job_reverses_stars_charge(monkeypatch):
    # A Stars-charged service (avatar) records no pack/credit on the job — the charge
    # lives in the transactions ledger. refund_job must issue the real Stars refund AND
    # mark the ledger, so the stuck-job sweep doesn't leave a swept avatar job charged.
    from sqlalchemy import select

    from core.models import GenerationJob, Transaction, User
    from core.services.refunds import refund_job

    bot = _FakeBot()
    monkeypatch.setattr("core.bot_client.get_bot", lambda: bot)

    async with SessionFactory() as s:
        s.add(User(user_id=1030, language_code="ru"))
        s.add(Transaction(
            user_id=1030, product="avatar", amount=400, currency="stars",
            gateway="stars", gateway_tx_id="charge_av_1", status="paid",
        ))
        job = GenerationJob(user_id=1030, service="avatar", pack_type=None,
                            cost_credits=0, params={"count": 100}, status="failed")
        s.add(job)
        await s.commit()

        await refund_job(s, job)
        tx = (await s.scalars(select(Transaction))).one()
        assert tx.status == "refunded"
        assert bot.refunded == [(1030, "charge_av_1")]

        # idempotent: a second sweep finds no paid tx → no second money refund
        await refund_job(s, job)
        assert bot.refunded == [(1030, "charge_av_1")]


async def test_refund_targets_the_exact_charge_not_the_newest(monkeypatch):
    # A user with TWO paid avatar purchases: the FAILED job stores its own charge id,
    # so the refund must reverse THAT tx — not just the newest (which may be a second
    # purchase whose job is still running).
    from sqlalchemy import select

    from core.models import GenerationJob, Transaction, User
    from core.services.refunds import refund_job

    bot = _FakeBot()
    monkeypatch.setattr("core.bot_client.get_bot", lambda: bot)

    async with SessionFactory() as s:
        s.add(User(user_id=1031, language_code="ru"))
        s.add(Transaction(user_id=1031, product="avatar", amount=400, currency="stars",
                          gateway="stars", gateway_tx_id="charge_OLD", status="paid"))
        s.add(Transaction(user_id=1031, product="avatar", amount=400, currency="stars",
                          gateway="stars", gateway_tx_id="charge_NEW", status="paid"))
        # The failing job is the OLDER purchase.
        job = GenerationJob(user_id=1031, service="avatar", pack_type=None, cost_credits=0,
                            params={"count": 100, "charge_id": "charge_OLD"}, status="failed")
        s.add(job)
        await s.commit()

        await refund_job(s, job)
        assert bot.refunded == [(1031, "charge_OLD")]  # not charge_NEW
        rows = {t.gateway_tx_id: t.status for t in (await s.scalars(select(Transaction))).all()}
        assert rows == {"charge_OLD": "refunded", "charge_NEW": "paid"}


async def test_stars_refund_failure_leaves_tx_paid(monkeypatch):
    # Money-first: if the real Telegram refund FAILS, the ledger must stay 'paid'
    # (accurate / retryable), never a false 'refunded'.
    from sqlalchemy import select

    from core.models import GenerationJob, Transaction, User
    from core.services.refunds import refund_job

    bot = _FakeBot(fail=True)
    monkeypatch.setattr("core.bot_client.get_bot", lambda: bot)

    async with SessionFactory() as s:
        s.add(User(user_id=1032, language_code="ru"))
        s.add(Transaction(user_id=1032, product="avatar", amount=400, currency="stars",
                          gateway="stars", gateway_tx_id="charge_av_2", status="paid"))
        job = GenerationJob(user_id=1032, service="avatar", pack_type=None, cost_credits=0,
                            params={"count": 100, "charge_id": "charge_av_2"}, status="failed")
        s.add(job)
        await s.commit()

        await refund_job(s, job)
        tx = (await s.scalars(select(Transaction))).one()
        assert tx.status == "paid"        # NOT 'refunded' — the money never went back
        assert bot.refunded == []


async def test_stars_refund_rechecks_status_under_lock(monkeypatch):
    """AUDIT-G2 (P1): peek_refundable_stars_tx runs BEFORE the FOR UPDATE lock, so two
    racers (the per-service worker + the stuck-job sweep) can both read 'paid' and both
    reach the real bot.refund_star_payment — issuing a DOUBLE real Telegram refund for
    the same charge. After taking the lock, refund_stars must re-check the tx is still
    'paid' and skip the external refund otherwise."""
    from core.models import Transaction, User
    from core.services.refunds import refund_stars

    bot = _FakeBot()
    monkeypatch.setattr("core.bot_client.get_bot", lambda: bot)

    # Simulate the race window: peek returns the charge id even though a concurrent
    # refunder already flipped the tx to 'refunded' while we waited on the lock.
    async def _peek(*a, **k):
        return "charge_race"

    monkeypatch.setattr("core.services.billing.peek_refundable_stars_tx", _peek)

    async with SessionFactory() as s:
        s.add(User(user_id=1040, language_code="ru"))
        s.add(Transaction(user_id=1040, product="avatar", amount=400, currency="stars",
                          gateway="stars", gateway_tx_id="charge_race", status="refunded"))
        await s.commit()

        ok = await refund_stars(s, 1040, "avatar", charge_id="charge_race")
        assert ok is False
        assert bot.refunded == [], "issued a second real Telegram refund for an already-refunded charge"


async def test_avatar_worker_refunds_exact_charge(monkeypatch):
    # The avatar worker (no provider yet) refunds the exact Stars charge the job paid
    # for and marks the job failed.
    from sqlalchemy import select

    from core.models import GenerationJob, Transaction, User
    from workers.avatar_tasks import process_avatar_job

    bot = _FakeBot()
    monkeypatch.setattr("core.bot_client.get_bot", lambda: bot)

    async with SessionFactory() as s:
        s.add(User(user_id=1033, language_code="ru"))
        s.add(Transaction(user_id=1033, product="avatar", amount=400, currency="stars",
                          gateway="stars", gateway_tx_id="charge_w", status="paid"))
        job = GenerationJob(user_id=1033, service="avatar", status="pending",
                            params={"count": 100, "charge_id": "charge_w"})
        s.add(job)
        await s.commit()
        job_id = job.job_id

    await process_avatar_job(None, job_id)

    async with SessionFactory() as s:
        j = await s.get(GenerationJob, job_id)
        assert j.status == "failed" and "refunded" in (j.error or "")
        tx = (await s.scalars(select(Transaction))).one()
        assert tx.status == "refunded"
    assert bot.refunded == [(1033, "charge_w")]
