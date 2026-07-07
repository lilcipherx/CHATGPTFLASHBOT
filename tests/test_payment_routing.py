"""Stars payment routing (regression for a critical money bug).

gift.router is registered BEFORE premium.router and both react to
``F.successful_payment``. aiogram stops event propagation after the first matching
handler runs, so gift's handler MUST only match ``gift:`` payloads — otherwise it
consumes every Stars payment and premium/pack/credits/avatar purchases are never
activated nor refunded.

We assert this by evaluating the gift router's message-handler FILTERS directly
(no re-parenting of the singleton router), so the test is about routing, not the
handler bodies.
"""
from __future__ import annotations

from types import SimpleNamespace

from bot.handlers import gift, premium


def _payment(payload: str | None):
    sp = SimpleNamespace(invoice_payload=payload) if payload is not None else None
    return SimpleNamespace(successful_payment=sp, text=None, caption=None)


async def _any_handler_matches(router, event) -> bool:
    """True if any of the router's message-handler filter sets match ``event``.

    A dummy ``bot`` is supplied because the Command filter requires it; it is never
    actually used here (these events carry text=None, so Command short-circuits)."""
    for handler in router.message.handlers:
        result, _ = await handler.check(event, bot=SimpleNamespace())
        if result:
            return True
    return False


async def test_gift_router_ignores_non_gift_payments():
    # Premium / pack / credits / avatar Stars payments must NOT match gift -> they
    # fall through to premium.py instead of being silently consumed.
    for payload in ("sub:premium:1", "credits:500", "image_pack:100", "avatar"):
        assert await _any_handler_matches(gift.router, _payment(payload)) is False


async def test_gift_router_owns_gift_payments():
    assert await _any_handler_matches(gift.router, _payment("gift:sub:premium:1")) is True


async def test_premium_router_handles_non_gift_payments():
    # premium.py owns the broad successful_payment handler -> it matches a normal buy.
    assert await _any_handler_matches(premium.router, _payment("sub:premium:1")) is True


async def test_pre_checkout_approves_all_our_payloads_including_gift():
    # premium.pre_checkout is the ONLY pre_checkout handler -> it must approve every
    # payload our invoices create, gift: included, and reject anything else.
    from bot.handlers.premium import pre_checkout
    from core.i18n import Translator

    async def _check(payload: str) -> bool:
        captured = {}

        async def _answer(*, ok: bool, error_message=None):
            captured["ok"] = ok

        await pre_checkout(
            SimpleNamespace(invoice_payload=payload, answer=_answer), Translator("ru")
        )
        return captured["ok"]

    for ok_payload in ("sub:premium:1", "pack:image_pack:100", "credits:500",
                       "avatar", "gift:sub:premium:1", "gift:pack:image_pack:100"):
        assert await _check(ok_payload) is True, ok_payload
    for bad_payload in ("", "evil:1", "random"):
        assert await _check(bad_payload) is False, bad_payload
