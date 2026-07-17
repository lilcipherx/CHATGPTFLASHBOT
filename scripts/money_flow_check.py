"""Self-contained money-flow e2e: a signed gateway webhook drives the REAL payment
pipeline end to end, with no real gateway or Telegram.

Covers (via the live /webhook/crypto route + apply_event, in-process ASGI):
  1. subscription activation  (signed CryptoBot invoice_paid -> activate_subscription)
  2. webhook idempotency      (replay the same invoice -> NO double-extension)
  3. amount-tampering rejected (paid amount != quoted -> no activation)
  4. credit-pack purchase     (credits:<uid>:<qty> payload -> credits added)
  5. Stripe fail-closed (P0)  (forged "paid" event with no webhook secret -> rejected,
                               no free subscription)
  6. refund                   (revoke_entitlement + _refund_at_gateway -> access lost,
                               tx=refund_pending for a manual-refund gateway)

Exit 0 = all checks passed, 1 = a check failed. Hermetic: SQLite + fakeredis;
Telegram delivery stubbed. Everything else (signature verify, apply_event, billing,
refund) is production code. Intended as a CI job so a money-pipeline regression
fails the build without real gateway keys.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{tempfile.gettempdir()}/aibot_money_{os.getpid()}.db")
os.environ.setdefault("REDIS_URL", "memory://")
os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ["CRYPTO_PAY_TOKEN"] = "test-crypto-token"
# Stripe is "available" (secret key set) but its WEBHOOK secret is intentionally
# left unset — the P0 fail-closed scenario: a forged "paid" event must be rejected.
os.environ["STRIPE_SECRET"] = "sk_test_forgerycheck"
os.environ.pop("STRIPE_WEBHOOK_SECRET", None)

TOKEN = os.environ["CRYPTO_PAY_TOKEN"]


def _sign(body: bytes) -> str:
    secret = hashlib.sha256(TOKEN.encode()).digest()
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def _webhook(payload_str: str, minor: int, invoice_id: str) -> tuple[bytes, str]:
    body = json.dumps({
        "update_type": "invoice_paid",
        "payload": {
            "status": "paid",
            "amount": f"{minor / 100:.2f}",
            "invoice_id": invoice_id,
            "payload": payload_str,
        },
    }).encode()
    return body, _sign(body)


async def run() -> int:
    from httpx import ASGITransport, AsyncClient

    import core.bot_client as bc
    bc.get_bot = lambda: _FakeBot()

    from api.main import app
    from core.constants import CREDIT_PACKS, SUBSCRIPTION_PRICES
    from core.db import SessionFactory, engine
    from core.models import Base, Transaction, User
    from core.payments.service import stars_to_minor
    from core.services.users import get_or_create_user

    UID, UID2 = 700001, 700002

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionFactory() as s:
        await get_or_create_user(s, UID)
        await get_or_create_user(s, UID2)
        await s.commit()

    async def user(uid):
        async with SessionFactory() as s:
            return await s.get(User, uid)

    results: list[tuple[str, bool]] = []

    def rec(label, ok, detail=""):
        results.append((label, ok))
        print(f"{'PASS' if ok else 'FAIL'}  {label:13} -> {detail}")

    prem_stars = SUBSCRIPTION_PRICES["premium"][1]
    prem_minor, _ = stars_to_minor(prem_stars, "crypto")
    inv1 = "inv-premium-1"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        hdr = {"content-type": "application/json"}

        async def post(body, sig):
            return await c.post(
                "/webhook/crypto", content=body,
                headers={**hdr, "crypto-pay-api-signature": sig},
            )

        # 1. Activation
        body, sig = _webhook(f"sub:{UID}:premium:1:{prem_minor}", prem_minor, inv1)
        r = await post(body, sig)
        u = await user(UID)
        rec("activation", r.status_code == 200 and u.sub_tier == "premium"
            and u.sub_expires is not None, f"http={r.status_code} tier={u.sub_tier}")
        expires_after_first = u.sub_expires

        # 2. Idempotency — replay the SAME invoice
        await post(body, sig)
        u = await user(UID)
        rec("idempotency", u.sub_expires == expires_after_first,
            "replay left expiry unchanged")

        # 3. Amount tampering — paid amount 5.00 higher than the quote (fresh user)
        bad = prem_minor + 500
        body2 = json.dumps({
            "update_type": "invoice_paid",
            "payload": {"status": "paid", "amount": f"{bad / 100:.2f}",
                        "invoice_id": "inv-tamper",
                        "payload": f"sub:{UID2}:premium:1:{prem_minor}"},
        }).encode()
        await post(body2, _sign(body2))
        u2 = await user(UID2)
        rec("amount-tamper", u2.sub_tier is None, "rejected, tier stayed None")

        # 4. Credit-pack purchase
        qty = sorted(CREDIT_PACKS)[0]
        cred_minor, _ = stars_to_minor(CREDIT_PACKS[qty], "crypto")
        before = (await user(UID)).credits
        body3, sig3 = _webhook(f"credits:{UID}:{qty}:{cred_minor}", cred_minor, "inv-credits")
        r = await post(body3, sig3)
        after = (await user(UID)).credits
        rec("credit-pack", r.status_code == 200 and after == before + qty,
            f"credits {before}->{after} (+{qty})")

        # 5. Stripe fail-closed (P0): with STRIPE_SECRET set but STRIPE_WEBHOOK_SECRET
        # unset, a forged "checkout.session.completed / paid" is rejected (verify_webhook
        # refuses an unverifiable event) — the user must NOT get a subscription for free.
        forged = json.dumps({
            "type": "checkout.session.completed",
            "data": {"object": {"payment_status": "paid",
                                 "metadata": {"payload": f"sub:{UID2}:premium:1:{prem_minor}"}}},
        }).encode()
        r = await c.post("/webhook/stripe", content=forged,
                         headers={**hdr, "stripe-signature": "t=1,v1=forged"})
        u2 = await user(UID2)
        rec("stripe-forgery", u2.sub_tier is None,
            f"forged Stripe 'paid' rejected (http={r.status_code}, tier stayed None)")

    # 6. Refund (revoke entitlement + attempt gateway refund) — same helpers the
    #    admin refund endpoint uses.
    try:
        from sqlalchemy import select

        from api.admin.ops import _refund_at_gateway
        from core.services.billing import revoke_entitlement
        async with SessionFactory() as s:
            tx = (await s.scalars(
                select(Transaction).where(Transaction.gateway_tx_id == inv1))).first()
            await revoke_entitlement(s, tx)
            tx.status = "refund_pending"
            gw_ok, _detail = await _refund_at_gateway(tx)
            if gw_ok:
                tx.status = "refunded"
            await s.commit()
            final_status = tx.status
        u = await user(UID)
        # crypto has no programmatic refund -> money refund stays pending, but the
        # entitlement is revoked immediately (user loses access).
        rec("refund", u.sub_tier is None and final_status == "refund_pending",
            f"tier={u.sub_tier} tx={final_status}")
    except Exception as e:
        rec("refund", False, f"{type(e).__name__}: {e}")

    fails = sum(1 for _, ok in results if not ok)

    await engine.dispose()
    try:
        os.remove(os.environ["DATABASE_URL"].split(":///")[1])
    except OSError:
        pass
    return fails


class _FakeBot:
    async def send_message(self, *a, **k): return None
    async def send_photo(self, *a, **k): return None
    async def refund_star_payment(self, *a, **k): return None


def main() -> int:
    fails = asyncio.run(run())
    if fails:
        print(f"\nMONEY-FLOW FAILED: {fails} check(s)")
        return 1
    print("\nMONEY-FLOW OK: activation, idempotency, tamper-reject, pack, stripe-forgery, refund")
    return 0


if __name__ == "__main__":
    sys.exit(main())
