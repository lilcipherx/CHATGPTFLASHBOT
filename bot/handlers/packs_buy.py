"""Pack purchase FSM (§12.1): pack → quantity → gateway → Stars invoice.

Entered from Gate#2 top-up buttons (`pack:<pack>`), the music paywall, or the
account screen. Stars activation adds credits idempotently via billing service."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, LabeledPrice
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.premium import _checkout_banner, _external_checkout
from bot.keyboards.inline import (
    pack_gateway_keyboard,
    pack_name,
    pack_qty_keyboard,
)
from core.constants import PACK_PRICES
from core.i18n import Translator
from core.models import User
from core.services import pricing, promos

router = Router()


@router.callback_query(F.data.startswith("pack:"))
async def cb_pack(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    pack = callback.data.split(":", 1)[1]
    if pack not in PACK_PRICES:
        await callback.answer()
        return
    # Don't sell a pack whose section is off (admin «Разделы» toggle) — the feature
    # would show "coming soon" anyway. Blocks every entry point to the buy flow.
    sec = await pricing.pack_section_state(session, pack)
    if not sec["enabled"]:
        await callback.answer()
        if callback.message:
            await callback.message.answer(sec["soon"])
        return
    banner, pct = await _checkout_banner(session, user, await pricing.sale_state(session), _)
    prices = await pricing.pack_prices_for(session, pack, apply_sale=False)
    await callback.message.answer(
        banner + _("pack.choose", name=pack_name(_, pack)),
        reply_markup=pack_qty_keyboard(_, pack, prices, pct),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("packqty:"))
async def cb_pack_qty(callback: CallbackQuery, _: Translator) -> None:
    # FIX: B11 - wrap callback_data parse in try/except (mirror contests.py:55-59).
    try:
        _p, pack, qty = callback.data.split(":")
        qty = int(qty)
    except (IndexError, ValueError):
        await callback.answer()
        return
    await callback.message.edit_text(
        _("premium.choose_gateway"),
        reply_markup=pack_gateway_keyboard(_, pack, qty),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("packpay:"))
async def cb_pack_pay(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    # FIX: B11 - wrap callback_data parse in try/except (mirror contests.py:55-59).
    try:
        _p, gateway, pack, qty = callback.data.split(":")
        qty = int(qty)
    except (IndexError, ValueError):
        await callback.answer()
        return
    # Defence in depth: even if a stale keyboard surfaces the button, a section that
    # was turned off can't be charged.
    if not (await pricing.pack_section_state(session, pack))["enabled"]:
        await callback.answer()
        return
    base = await pricing.pack_price(session, pack, qty, apply_sale=False)
    if base is None:
        await callback.answer()
        return
    price = pricing.discount(base, await promos.checkout_percent(session, user))
    title = f"{pack_name(_, pack)} — {qty} {_('unit.generations')}"
    # Abandoned-cart tracking (ТЗ §7): the «resume» button re-opens this pack's menu.
    from core.services import checkout
    await checkout.record_intent(
        session, user.user_id, kind="pack", resume_cb=f"pack:{pack}",
        gateway=gateway, amount=price,
    )

    if gateway == "stars":
        await callback.message.answer_invoice(
            title=title,
            description=_("pay.pack_invoice_desc", title=title),
            payload=f"pack:{pack}:{qty}",
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=price)],
        )
        await callback.answer()
        return

    await _external_checkout(
        callback, gateway, f"pack:{user.user_id}:{pack}:{qty}", price, title, _
    )
