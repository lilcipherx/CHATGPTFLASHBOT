"""/gift — buy a subscription / pack for a friend, pay with Telegram Stars, share
a redeem code (ТЗ §6). /redeem <code> claims a gift.

This router runs ALONGSIDE premium.py's global successful_payment handler: our
own successful_payment handler acts ONLY on ``gift:`` payloads and returns
silently for everything else, so premium's handler still processes its own
payments (aiogram dispatches to all matching routers in include order)."""
from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n import Translator
from core.models import User
from core.services import gifts, pricing

router = Router()
log = structlog.get_logger()

# Gift anything you can buy for yourself: any subscription (Premium / Premium ×2,
# every duration) and any generation pack (image/video/music, every quantity). The
# flow drills down to the terminal callbacks gift:sub:<product>:<months> and
# gift:pack:<pack>:<qty>, which build the Stars invoice (cb_gift below). All amounts
# come from the live admin pricing, so a price change in the panel is reflected here.
_SUB_PRODUCTS = ("premium", "premium_x2")
_PACKS = ("image_pack", "video_pack", "music_pack")
_PACK_BTN = {
    "image_pack": "premium.btn_image",
    "video_pack": "premium.btn_video",
    "music_pack": "premium.btn_music",
}


def _root_menu(_: Translator) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_("gift.btn_sub"), callback_data="gift:menu:sub")],
        [InlineKeyboardButton(text=_("gift.btn_pack_menu"), callback_data="gift:menu:pack")],
    ])


@router.message(Command("gift"))
async def cmd_gift(message: Message, _: Translator) -> None:
    await message.answer(_("gift.choose"), reply_markup=_root_menu(_))


@router.callback_query(F.data == "gift:root")
async def cb_gift_root(callback: CallbackQuery, _: Translator) -> None:
    if callback.message:
        await callback.message.edit_text(_("gift.choose"), reply_markup=_root_menu(_))
    await callback.answer()


@router.callback_query(F.data == "gift:menu:sub")
async def cb_gift_menu_sub(callback: CallbackQuery, _: Translator) -> None:
    """Pick which subscription to gift (Premium / Premium ×2)."""
    rows = [
        [InlineKeyboardButton(text=_(f"premium.btn_{p}"), callback_data=f"gift:subprod:{p}")]
        for p in _SUB_PRODUCTS
    ]
    rows.append([InlineKeyboardButton(text=_("btn.back"), callback_data="gift:root")])
    if callback.message:
        await callback.message.edit_text(
            _("gift.choose"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("gift:subprod:"))
async def cb_gift_subprod(
    callback: CallbackQuery, session: AsyncSession, _: Translator
) -> None:
    """Pick the duration for the chosen subscription — prices from live admin config."""
    product = callback.data.split(":")[2]
    prices = await pricing.subscription_prices(session, product)
    rows = [
        [InlineKeyboardButton(
            text=f"{_('duration.' + str(months))} — {price} ⭐",
            callback_data=f"gift:sub:{product}:{months}",
        )]
        for months, price in prices.items()
    ]
    rows.append([InlineKeyboardButton(text=_("btn.back"), callback_data="gift:menu:sub")])
    if callback.message:
        await callback.message.edit_text(
            _("gift.choose"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    await callback.answer()


@router.callback_query(F.data == "gift:menu:pack")
async def cb_gift_menu_pack(
    callback: CallbackQuery, session: AsyncSession, _: Translator
) -> None:
    """Pick which pack to gift — only sections that are enabled are offered."""
    rows = []
    for pack in _PACKS:
        sec = await pricing.pack_section_state(session, pack)
        if sec["enabled"]:
            rows.append([InlineKeyboardButton(
                text=_(_PACK_BTN[pack]), callback_data=f"gift:packtype:{pack}")])
    if not rows:
        await callback.answer()
        if callback.message:
            await callback.message.answer(_("gift.pack_none"))
        return
    rows.append([InlineKeyboardButton(text=_("btn.back"), callback_data="gift:root")])
    if callback.message:
        await callback.message.edit_text(
            _("gift.choose"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("gift:packtype:"))
async def cb_gift_packtype(
    callback: CallbackQuery, session: AsyncSession, _: Translator
) -> None:
    """Pick the quantity for the chosen pack — prices from live admin config."""
    pack = callback.data.split(":")[2]
    prices = await pricing.pack_prices_for(session, pack)
    unit = _("unit.generations")
    rows = [
        [InlineKeyboardButton(
            text=f"{qty} {unit} — {price} ⭐", callback_data=f"gift:pack:{pack}:{qty}")]
        for qty, price in prices.items()
    ]
    rows.append([InlineKeyboardButton(text=_("btn.back"), callback_data="gift:menu:pack")])
    if callback.message:
        await callback.message.edit_text(
            _("gift.choose"), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("gift:sub:") | F.data.startswith("gift:pack:"))
async def cb_gift(callback: CallbackQuery, session: AsyncSession, _: Translator) -> None:
    # FIX: B10 - wrap callback_data parse in try/except so a forged/malformed
    # payload (gift:sub:foo / gift:pack:img:abc) doesn't crash the handler.
    try:
        _p, kind, product, value = callback.data.split(":")
        value = int(value)
    except (IndexError, ValueError):
        await callback.answer()
        return
    if kind == "sub":
        price = await pricing.subscription_price(session, product, value)
        title = _("gift.invoice_title_sub", product=product, value=value)
    elif kind == "pack":
        # A pack gift follows the same section gate as buying it for yourself.
        sec = await pricing.pack_section_state(session, product)
        if not sec["enabled"]:
            await callback.answer()
            if callback.message:
                await callback.message.answer(sec["soon"])
            return
        price = await pricing.pack_price(session, product, value)
        title = f"🎁 {product} · {value}"
    else:
        await callback.answer()
        return
    if price is None:
        await callback.answer()
        return

    await callback.message.answer_invoice(
        title=title,
        description=_("gift.invoice_desc", title=title),
        # gift:<kind>:<product>:<months_or_qty> — read back in successful_payment.
        payload=f"gift:{kind}:{product}:{value}",
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=price)],
    )
    await callback.answer()


# Match ONLY gift: payloads. A bare F.successful_payment here would consume EVERY
# Stars payment (this router is registered before premium.py): aiogram stops event
# propagation after the first matching handler returns, so a non-gift payment that
# this handler merely `return`s on would NEVER reach premium.py — the purchase would
# be neither activated nor refunded. Narrowing the filter lets non-gift payments fall
# through to premium.py's handler. (None-safe: no successful_payment → no match.)
@router.message(F.successful_payment.invoice_payload.startswith("gift:"))
async def on_gift_payment(
    message: Message, session: AsyncSession, user: User, _: Translator
) -> None:
    """Create the Gift for a paid ``gift:`` invoice and return the shareable code."""
    sp = message.successful_payment
    payload = sp.invoice_payload or ""

    parts = payload.split(":")
    if len(parts) != 4 or not parts[3].isdigit():
        log.error("gift.bad_payload", payload=payload, user_id=user.user_id)
        return
    kind, product, value = parts[1], parts[2], int(parts[3])
    months = value if kind == "sub" else None
    qty = value if kind == "pack" else None

    # FIX: #3 - wrap create_gift in try/except so a DB failure after Stars are
    # collected doesn't lose the buyer's money (was: no try/except, unlike premium.py).
    # FIX: #4 - wrap the code-delivery message.answer in try/except so a transient
    # Telegram error doesn't lose the code. On duplicate delivery (gift is None),
    # re-fetch the existing gift by charge_id and re-send its code.
    try:
        gift = await gifts.create_gift(
            session,
            buyer_id=user.user_id,
            kind=kind,
            product=product,
            months=months,
            qty=qty,
            gateway="stars",
            amount=sp.total_amount,
            gateway_tx_id=sp.telegram_payment_charge_id,
        )
    except Exception as exc:  # noqa: BLE001 — gift creation failed AFTER Stars taken
        log.error("gift.create_failed", error=str(exc), user_id=user.user_id,
                  charge_id=sp.telegram_payment_charge_id)
        from bot.handlers.premium import _refund_stars
        await _refund_stars(message, user.user_id, sp.telegram_payment_charge_id, _)
        return

    if gift is None:
        # FIX: #4 - duplicate delivery: re-fetch the existing gift by charge_id and
        # re-send its code (was: silently returned, code never delivered).
        from core.models.gift import Gift
        from sqlalchemy import select
        existing = await session.scalar(
            select(Gift).where(Gift.gateway_tx_id == sp.telegram_payment_charge_id)
        )
        if existing is None:
            return
        gift = existing

    try:
        me = await message.bot.get_me()
        link = f"https://t.me/{me.username}?start=redeem_{gift.code}"
        await message.answer(
            _("gift.paid", code=gift.code, link=link),
            disable_web_page_preview=True,
        )
    except Exception as exc:  # noqa: BLE001 — FIX: #4 - code delivery failed
        log.error("gift.code_delivery_failed", user_id=user.user_id, code=gift.code, error=str(exc))


@router.message(Command("redeem"))
async def cmd_redeem(
    message: Message, command: CommandObject, session: AsyncSession, user: User,
    _: Translator,
) -> None:
    code = (command.args or "").strip()
    if not code:
        await message.answer(_("redeem.usage"))
        return
    _ok, text = await gifts.redeem_gift(session, code, user)
    await message.answer(text)
