"""/premium — 3-step purchase FSM (§12.1): product → duration → gateway → invoice.

Telegram Stars is implemented natively (XTR invoice + pre_checkout +
successful_payment). External gateways (СБП/ЮКасса/Stripe) create a pending
transaction and hand off to the web-view flow handled by the API webhooks."""
from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline import (
    gateway_keyboard,
    premium_durations,
    premium_products,
    promo_banner,
    sale_banner,
)
from bot.states import AvatarSG
from core.config import settings
from core.constants import SUBSCRIPTION_PRICES
from core.i18n import Translator, all_labels
from core.models import User
from core.payments import PaymentError
from core.payments.service import create_checkout
from core.services import pricing, promos
from core.services.billing import (
    activate_subscription,
    add_credits,
    add_pack_credits,
    record_one_time,
)

router = Router()
log = structlog.get_logger()


def _sub_title(_: Translator, product: str, months: int) -> str:
    return f"{_('product.' + product)} | {_('duration.' + str(months))}"


_PACKS = ("image_pack", "video_pack", "music_pack")


async def _enabled_packs(session: AsyncSession) -> set[str]:
    """Packs whose media section is ON — only those are offered/sold."""
    return {p for p in _PACKS if (await pricing.pack_section_state(session, p))["enabled"]}


async def _premium_text_prices(session: AsyncSession) -> dict[str, int]:
    """Live prices shown INSIDE the /premium overview text, so an admin price change
    in the panel is reflected in the description — not just on the buttons. Base
    (pre-sale) prices: the active sale is already announced by the banner above the
    text, so the overview lists the regular price to avoid a confusing double discount."""
    def _from(m: dict[int, int]) -> int:
        vals = [v for v in m.values() if v > 0]
        return min(vals) if vals else 0
    return {
        "p_premium": await pricing.subscription_price(
            session, "premium", 1, apply_sale=False) or 0,
        "p_premium_x2": await pricing.subscription_price(
            session, "premium_x2", 1, apply_sale=False) or 0,
        "p_image_from": _from(await pricing.pack_prices_for(
            session, "image_pack", apply_sale=False)),
        "p_video_from": _from(await pricing.pack_prices_for(
            session, "video_pack", apply_sale=False)),
        "p_music_from": _from(await pricing.pack_prices_for(
            session, "music_pack", apply_sale=False)),
    }


async def _checkout_banner(
    session: AsyncSession, user: User, sale: dict, _: Translator
) -> tuple[str, int]:
    """(banner, effective_percent) for a buy menu: the operative discount is the larger
    of the global sale and the user's applied promo code (they don't stack — ТЗ §4). The
    banner shows whichever one is operative; the percent drives the price labels."""
    sale_pct = sale["percent"] if sale["active"] else 0
    promo_pct = await promos.active_discount(session, user)
    if promo_pct > 0 and promo_pct >= sale_pct:
        return promo_banner(_, promo_pct), promo_pct
    return sale_banner(_, sale), sale_pct


@router.message(Command("premium"))
@router.message(F.text.in_(all_labels("btn.premium")))
async def cmd_premium(
    message: Message, session: AsyncSession, user: User, _: Translator
) -> None:
    banner, _pct = await _checkout_banner(session, user, await pricing.sale_state(session), _)
    await message.answer(
        banner + _("premium", support=settings.support_contact,
                    **await _premium_text_prices(session)),
        reply_markup=premium_products(_, await _enabled_packs(session)),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "premium:open")
async def cb_premium_open(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    banner, _pct = await _checkout_banner(session, user, await pricing.sale_state(session), _)
    await callback.message.edit_text(
        banner + _("premium", support=settings.support_contact,
                    **await _premium_text_prices(session)),
        reply_markup=premium_products(_, await _enabled_packs(session)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prem:"))
async def cb_product(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    product = callback.data.split(":", 1)[1]
    if product not in SUBSCRIPTION_PRICES:
        await callback.answer()
        return
    sale = await pricing.sale_state(session)
    banner, pct = await _checkout_banner(session, user, sale, _)
    prices = await pricing.subscription_prices(session, product, apply_sale=False)
    await callback.message.edit_text(
        banner + _("premium.choose_duration"),
        reply_markup=premium_durations(_, product, prices, pct),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("premdur:"))
async def cb_duration(callback: CallbackQuery, user: User, _: Translator) -> None:
    # FIX: B12 - wrap callback_data parse in try/except (mirror contests.py:55-59).
    try:
        _p, product, months = callback.data.split(":")
        months = int(months)
    except (IndexError, ValueError):
        await callback.answer()
        return
    text = _("premium.choose_gateway")
    # Switching tier while a different plan is still active: the remaining time
    # continues under the NEW tier (plans stack by time) — make that explicit.
    if user.is_premium and user.sub_tier and user.sub_tier != product:
        text = (
            _("premium.upgrade_warning",
              current=_("product." + user.sub_tier), new=_("product." + product))
            + "\n\n" + text
        )
    await callback.message.edit_text(
        text, reply_markup=gateway_keyboard(_, product, months),  # FIX: B12 - months already int
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay:"))
async def cb_pay(
    callback: CallbackQuery, session: AsyncSession, user: User, _: Translator
) -> None:
    # FIX: B12 - wrap callback_data parse in try/except (mirror contests.py:55-59).
    try:
        _p, gateway, product, months = callback.data.split(":")
        months = int(months)
    except (IndexError, ValueError):
        await callback.answer()
        return
    # Charge at max(sale, applied discount code): take the base price and apply the
    # effective checkout percent once (the two never stack — ТЗ §4).
    base = await pricing.subscription_price(session, product, months, apply_sale=False)
    if base is None:
        await callback.answer()
        return
    price = pricing.discount(base, await promos.checkout_percent(session, user))
    title = _sub_title(_, product, months)
    # Abandoned-cart tracking (ТЗ §7): record the intent at the pay step; the «resume»
    # button on the reminder re-opens this product's duration menu.
    from core.services import checkout
    await checkout.record_intent(
        session, user.user_id, kind="sub", resume_cb=f"prem:{product}",
        gateway=gateway, amount=price,
    )

    if gateway == "stars":
        await callback.message.answer_invoice(
            title=title,
            description=_("pay.sub_invoice_desc", title=title),
            payload=f"sub:{product}:{months}",
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=price)],
        )
        await callback.answer()
        return

    await _external_checkout(
        callback, gateway, f"sub:{user.user_id}:{product}:{months}", price, title, _
    )


async def _external_checkout(
    callback: CallbackQuery, gateway: str, payload: str, stars_price: int,
    title: str, _: Translator,
) -> None:
    """Create an external-gateway checkout and present a pay-link button.
    Activation happens later via the gateway webhook (api/routers/webhooks.py)."""
    try:
        result = await create_checkout(
            gateway, stars_price=stars_price, payload=payload, description=title
        )
    except PaymentError:
        await callback.answer(_("pay.unavailable"), show_alert=True)
        return
    except Exception:  # noqa: BLE001
        await callback.answer(_("pay.failed"), show_alert=True)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("pay.link_btn", title=title), url=result.url)]
        ]
    )
    await callback.message.answer(_("pay.link"), reply_markup=kb)
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, _: Translator) -> None:
    # The ONLY pre_checkout handler (gift.py has none), so it must approve EVERY
    # payload our own invoices create — including gift: (gift.py answer_invoice),
    # or gift purchases are rejected before payment. Stars amounts are fixed
    # server-side at invoice time, so a well-formed payload is sufficient.
    payload = query.invoice_payload or ""
    ok = (
        payload.startswith(("sub:", "pack:", "credits:", "gift:")) or payload == "avatar"
    )
    await query.answer(ok=ok, error_message=None if ok else _("pay.precheckout_unavailable"))


async def _refund_stars(
    message: Message, user_id: int, charge_id: str | None, _: Translator
) -> None:
    """Refund a Stars charge whose entitlement could not be granted, so the user
    is never charged for nothing. Best-effort + tells the user."""
    if charge_id:
        try:
            await message.bot.refund_star_payment(
                user_id=user_id, telegram_payment_charge_id=charge_id
            )
        except Exception:  # noqa: BLE001
            log.error("stars.refund_failed", user_id=user_id, charge_id=charge_id)
    try:
        await message.answer(_("pay.activate_failed"))
    except Exception:  # noqa: BLE001
        pass


async def _apply_stars_payment(
    session: AsyncSession, state: FSMContext, user: User, sp, _: Translator
) -> str | None:
    """Grant the entitlement for a verified Stars payment. Returns the success
    message (or None for an unknown/duplicate event). Raises on a real activation
    failure so the caller can refund. Activation is idempotent on the charge id."""
    payload = sp.invoice_payload or ""
    amount = sp.total_amount
    tx = sp.telegram_payment_charge_id
    parts = payload.split(":")
    kind = parts[0] if parts else ""

    if kind == "sub" and len(parts) == 3 and parts[2].isdigit():
        product, months = parts[1], int(parts[2])
        if await activate_subscription(session, user, product=product, months=months,
                                       gateway="stars", amount=amount, gateway_tx_id=tx):
            return _("pay.sub_activated", title=_sub_title(_, product, months))
        return None
    if kind == "pack" and len(parts) == 3 and parts[2].isdigit():
        pack, qty = parts[1], int(parts[2])
        kind_short = pack.replace("_pack", "")
        if await add_pack_credits(session, user, pack=pack, qty=qty, gateway="stars",
                                  amount=amount, gateway_tx_id=tx):
            return _("pay.pack_added", qty=qty, unit=_("unit.generations"),
                     pack=_(f"pack.name.{kind_short}"))
        return None
    if kind == "credits" and len(parts) == 2 and parts[1].isdigit():
        qty = int(parts[1])
        if await add_credits(session, user, qty=qty, gateway="stars",
                             amount=amount, gateway_tx_id=tx):
            return _("pay.credits_added", qty=qty)
        return None
    if payload == "avatar":
        if await record_one_time(session, user, product="avatar", gateway="stars",
                                 amount=amount, gateway_tx_id=tx):
            # FIX: AUDIT-16 - create GenerationJob(service='avatar', status='awaiting_selfie')
            # at payment time so the stuck-job sweep can refund if the user never sends a selfie
            from core.models import GenerationJob
            job = GenerationJob(
                user_id=user.user_id,
                service="avatar",
                status="awaiting_selfie",
                pack_type="stars",
                cost_credits=0,
                params={"charge_id": tx, "amount": amount},
            )
            session.add(job)
            await session.commit()
            await state.set_state(AvatarSG.awaiting_selfie)
            # Remember THIS purchase's charge id so the worker refunds the exact tx if
            # generation can't be delivered (not just the newest avatar tx).
            await state.update_data(avatar_charge_id=tx, avatar_job_id=job.job_id)
            return _("pay.avatar_paid")
        return None

    # Unrecognised payload — log and refund (we took money for nothing we know).
    log.error("stars.unknown_payload", payload=payload, user_id=user.user_id)
    raise ValueError(f"unknown payload {payload!r}")


@router.message(F.successful_payment)
async def on_successful_payment(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    _: Translator,
) -> None:
    sp = message.successful_payment
    try:
        success = await _apply_stars_payment(session, state, user, sp, _)
    except Exception as exc:  # noqa: BLE001 — activation failed AFTER money taken
        log.error("stars.activation_failed", error=str(exc),
                  payload=sp.invoice_payload, user_id=user.user_id)
        await _refund_stars(message, user.user_id, sp.telegram_payment_charge_id, _)
        return
    # Reward the referrer on the referred user's first paid purchase (avatar is
    # excluded: it is refunded by the worker until a provider exists). Run this even
    # when success is None (an idempotent DUPLICATE successful_payment): the reward is
    # idempotent on its own (referrals.referred_id is unique), so a redelivered event
    # RECOVERS a reward that was lost when the process died between the purchase commit
    # and the reward commit — mirroring the external-gateway apply_event path. Reaching
    # here means a known payload was processed; unknown payloads raise above and refund.
    if (sp.invoice_payload or "") != "avatar":
        # FIX: AUDIT-12 - wrap each post-activation side-effect in try/except
        from core.services.referrals import notify_referrer, reward_referral_on_payment
        try:
            rewarded = await reward_referral_on_payment(session, user)
            if rewarded:
                await notify_referrer(*rewarded, reason="purchase")
        except Exception as exc:
            import structlog
            structlog.get_logger().warning("premium.referral_reward_failed", user_id=user.user_id, error=str(exc))
        try:
            from core.services.loyalty import check_and_notify_upgrade
            await check_and_notify_upgrade(session, user)
        except Exception as exc:
            import structlog
            structlog.get_logger().warning("premium.loyalty_check_failed", user_id=user.user_id, error=str(exc))
        try:
            from core.services.billing import notify_purchase_bonus
            await notify_purchase_bonus(session, user)
        except Exception as exc:
            import structlog
            structlog.get_logger().warning("premium.bonus_notify_failed", user_id=user.user_id, error=str(exc))
        try:
            await promos.consume_discount(session, user, sale_pct=await pricing.sale_percent(session))
        except Exception as exc:
            import structlog
            structlog.get_logger().warning("premium.discount_consume_failed", user_id=user.user_id, error=str(exc))
        try:
            from core.services import checkout
            await checkout.mark_completed(session, user.user_id)
        except Exception as exc:
            import structlog
            structlog.get_logger().warning("premium.checkout_mark_failed", user_id=user.user_id, error=str(exc))
    # FIX: AUDIT12-4 - removed the duplicate unwrapped block that re-ran loyalty,
    # notify_purchase_bonus, consume_discount and mark_completed AFTER the AUDIT-12
    # wrapped block above (L324-355). The duplicate consumed single-use promo codes
    # twice and could double-fire loyalty notifications. The wrapped block is the
    # canonical one.
    # Confirmation only for a freshly-applied grant — None means an idempotent
    # duplicate, where there is nothing new to announce. A failure to SEND the
    # confirmation must NOT trigger a refund of a real grant.
    if success:
        try:
            await message.answer(success)
        except Exception:  # noqa: BLE001
            pass
