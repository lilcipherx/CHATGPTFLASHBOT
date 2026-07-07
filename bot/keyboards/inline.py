"""Inline keyboards for menus, model selection, settings and premium flow."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.config import settings
from core.constants import (
    ALL_VOICES,
    GATEWAYS,
    LANGUAGES,
    PACK_LABELS,
    PACK_PRICES,
    SUBSCRIPTION_PRICES,
    TEXT_MODELS,
    VOICES_FEMALE,
)
from core.i18n import Translator
from core.services import pricing


def fiat_hint(stars: int) -> str:
    """Approximate fiat suffix for a Stars price, e.g. ' (≈ 600 ₽)'.

    Returns '' when the rate is unset/0 so labels never show '0 ₽' noise.
    The Stars amount stays authoritative; '≈' marks the ₽ as a rough guide."""
    rate = settings.stars_to_rub
    if not rate or stars <= 0:
        return ""
    return f" (≈ {round(stars * rate)} ₽)"


def price_tag(orig: int, sale_pct: int) -> str:
    """Plain-text price label for a buy button. With an active sale (``sale_pct`` > 0)
    shows the pre-sale price → discounted price and the percent, e.g.
    ``1000→800 ⭐ −20% (≈ …₽)``; otherwise just ``800 ⭐ (≈ …₽)``. Button text is plain
    (no markdown), so the original is shown with an arrow rather than a strike. The
    discount uses the same rounding as the charge path, so the two always agree."""
    if sale_pct > 0:
        final = pricing.discount(orig, sale_pct)
        return f"{orig}→{final} ⭐ −{sale_pct}%{fiat_hint(final)}"
    return f"{orig} ⭐{fiat_hint(orig)}"


def _sale_time_left(_: Translator, until_iso: Any) -> str:
    """Localized compact countdown to ``until_iso`` (''=no/expired/blank)."""
    if not until_iso:
        return ""
    try:
        end = datetime.fromisoformat(str(until_iso))
    except ValueError:
        return ""
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    secs = (end - datetime.now(UTC)).total_seconds()
    if secs <= 0:
        return ""
    d, rem = divmod(int(secs), 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d > 0:
        return _("sale.left_dh", d=d, h=h)
    if h > 0:
        return _("sale.left_hm", h=h, m=m)
    return _("sale.left_m", m=max(1, m))


def sale_banner(_: Translator, sale: dict) -> str:
    """A ``🔥 Распродажа −X% · ⏳ до конца: …`` banner block (with trailing blank line)
    for buy menus, or '' when no sale is active. ``sale`` is pricing.sale_state()."""
    if not sale.get("active"):
        return ""
    line = _("sale.banner", percent=int(sale.get("percent") or 0))
    left = _sale_time_left(_, sale.get("until"))
    if left:
        line += " · " + _("sale.ends_in", time=left)
    return line + "\n\n"


def promo_banner(_: Translator, percent: int) -> str:
    """A ``🏷 Промокод −X% применён`` banner block for buy menus when the user has an
    applied discount code (and it's the operative discount), or '' when percent<=0."""
    if percent <= 0:
        return ""
    return _("promo.applied_banner", percent=percent) + "\n\n"


# pack key -> i18n key for its localized plain name
PACK_NAME_KEY = {
    "image_pack": "pack.name.image",
    "video_pack": "pack.name.video",
    "music_pack": "pack.name.music",
}


def pack_name(_: Translator, pack: str) -> str:
    return _(PACK_NAME_KEY[pack])


def open_app_button(_: Translator) -> InlineKeyboardButton | None:
    """FIX: POLISH-11 - "Open App" WebApp button removed per owner request. The Mini
    App is still reachable via /start (the reply keyboard is pure-text now), but no
    inline WebApp button is appended to menus any more. Returns None so all callers
    (`open_app_markup`, `model_menu`, `photo_menu`, etc.) naturally drop the button."""
    return None


def open_app_markup(_: Translator) -> InlineKeyboardMarkup | None:
    btn = open_app_button(_)
    return InlineKeyboardMarkup(inline_keyboard=[[btn]]) if btn else None


def close_button(_: Translator) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_("btn.close"), callback_data="close")]]
    )


def gate_keyboard(_: Translator, channels: list[str]) -> InlineKeyboardMarkup:
    """Gate #1 card: subscribe-to-channel buttons + check + premium bypass."""
    rows: list[list[InlineKeyboardButton]] = []
    for ch in channels:
        # FIX: AUDIT-117 - validate channel format (only @username or bare username)
        if ch.startswith(("http://", "https://")) or ch.startswith("-"):
            continue  # skip URL/numeric ID entries — can't build a t.me link
        handle = ch.removeprefix("@")
        rows.append([InlineKeyboardButton(
            text=_("gate.btn_subscribe", channel=ch), url=f"https://t.me/{handle}"
        )])
    rows.append([InlineKeyboardButton(text=_("gate.btn_check"), callback_data="gate:check")])
    rows.append([InlineKeyboardButton(text=_("gate.btn_premium"), callback_data="premium:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def model_keyboard(
    _: Translator,
    active_key: str,
    models: list[tuple[str, str]] | None = None,
    premium_keys: set[str] | None = None,
) -> InlineKeyboardMarkup:
    """Model picker. `models` is an optional admin-controlled list of (key, title);
    when omitted, falls back to the static TEXT_MODELS catalog. `premium_keys` marks
    Premium-only models with a 💎 badge so a free user sees the upsell BEFORE tapping
    (the actual gate lives in cb_model); when omitted for the static catalog it is
    derived from TEXT_MODELS."""
    b = InlineKeyboardBuilder()
    items = models if models is not None else [(m.key, m.name) for m in TEXT_MODELS]
    if premium_keys is None:
        premium_keys = {m.key for m in TEXT_MODELS if m.premium} if models is None else set()
    for key, name in items:
        mark = "✅ " if key == active_key else ""
        badge = " 💎" if key in premium_keys else ""
        b.button(text=f"{mark}{name}{badge}", callback_data=f"model:{key}")
    b.button(text=_("btn.close"), callback_data="close")
    if models is None:
        b.adjust(1, 2, 2, 2, 2, 1)
    else:
        b.adjust(1)
    return b.as_markup()


def settings_keyboard(_: Translator) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=_("btn.set_model"), callback_data="settings:model")
    b.button(text=_("btn.set_role"), callback_data="settings:role")
    b.button(text=_("btn.set_context"), callback_data="settings:context")
    b.button(text=_("btn.set_voice"), callback_data="settings:voice")
    b.button(text=_("btn.set_lang"), callback_data="settings:lang")
    b.button(text=_("btn.close"), callback_data="close")
    b.adjust(2, 2, 1, 1)
    return b.as_markup()


def language_keyboard(_: Translator) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for code, label in LANGUAGES:
        b.button(text=label, callback_data=f"lang:{code}")
    b.button(text=_("btn.back"), callback_data="settings:open")
    b.adjust(2)
    return b.as_markup()


def onboarding_language_keyboard() -> InlineKeyboardMarkup:
    """First-run language picker (shown on the very first /start). Uses a distinct
    `onblang:` callback so choosing here PROCEEDS to the welcome, rather than
    re-rendering the settings screen like the in-settings picker. No back button —
    it's an onboarding step, not a sub-menu. Labels are native, so no Translator."""
    b = InlineKeyboardBuilder()
    for code, label in LANGUAGES:
        b.button(text=label, callback_data=f"onblang:{code}")
    b.adjust(2)
    return b.as_markup()


def voice_keyboard(_: Translator, active_voice: str, enabled: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for v in ALL_VOICES:
        mark = "✅ " if v == active_voice else ""
        gender = "♀" if v in VOICES_FEMALE else "♂"
        b.button(text=f"{mark}{v} {gender}", callback_data=f"voice:set:{v}")
    toggle = _("voice.on") if enabled else _("voice.off")
    b.button(text=toggle, callback_data="voice:toggle")
    b.button(text=_("settings.voice.preview"), callback_data="voice:preview")
    b.button(text=_("btn.back"), callback_data="settings:open")
    # 12 voices in 3 cols, then full-width controls
    b.adjust(3, 3, 3, 3, 1, 1, 1)
    return b.as_markup()


def account_keyboard(_: Translator, show_vip: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=_("btn.daily_bonus"), callback_data="bonus:claim")],
        [InlineKeyboardButton(text=_("btn.connect_premium"), callback_data="premium:open")],
    ]
    # The VIP-ladder button appears only when the loyalty program is enabled.
    if show_vip:
        rows.append([InlineKeyboardButton(text=_("btn.vip"), callback_data="vip:open")])
    app_btn = open_app_button(_)
    if app_btn:
        rows.insert(0, [app_btn])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def premium_products(
    _: Translator, packs_enabled: set[str] | None = None
) -> InlineKeyboardMarkup:
    """Premium subscription always shown; a generation-pack button appears only when
    its section is ON (``packs_enabled``). None = show all (back-compat / tests)."""
    if packs_enabled is None:
        packs_enabled = {"image_pack", "video_pack", "music_pack"}
    rows = [
        [InlineKeyboardButton(text=_("premium.btn_premium"), callback_data="prem:premium")],
        [InlineKeyboardButton(text=_("premium.btn_premium_x2"), callback_data="prem:premium_x2")],
    ]
    if "image_pack" in packs_enabled:
        rows.append([InlineKeyboardButton(
            text=_("premium.btn_image"), callback_data="pack:image_pack")])
    if "video_pack" in packs_enabled:
        rows.append([InlineKeyboardButton(
            text=_("premium.btn_video"), callback_data="pack:video_pack")])
    if "music_pack" in packs_enabled:
        rows.append([InlineKeyboardButton(
            text=_("premium.btn_music"), callback_data="pack:music_pack")])
    rows.append([InlineKeyboardButton(text=_("btn.close"), callback_data="close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ad_keyboard(_: Translator) -> InlineKeyboardMarkup:
    """CTA under a free-user ad: a button into the Premium menu (ad-free upsell, ТЗ §6)."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=_("ad.remove_btn"), callback_data="premium:open")
    ]])


def premium_durations(
    _: Translator, product: str, prices: dict[int, int] | None = None, sale_pct: int = 0
) -> InlineKeyboardMarkup:
    # `prices` (admin live config) overrides the static defaults when provided. When a
    # sale is active the handler passes PRE-sale prices + `sale_pct`, so each button
    # can show the original → discounted price.
    items = prices if prices is not None else SUBSCRIPTION_PRICES[product]
    b = InlineKeyboardBuilder()
    for months, price in items.items():
        b.button(
            text=f"{_('duration.' + str(months))} — {price_tag(price, sale_pct)}",
            callback_data=f"premdur:{product}:{months}",
        )
    b.button(text=_("btn.back"), callback_data="premium:open")
    b.adjust(1)
    return b.as_markup()


def pack_qty_keyboard(
    _: Translator, pack: str, prices: dict[int, int] | None = None, sale_pct: int = 0
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    labels = PACK_LABELS.get(pack, {})
    unit = _("unit.generations")
    # On sale the handler passes PRE-sale prices + `sale_pct` (original → discounted).
    items = prices if prices is not None else PACK_PRICES[pack]
    for qty, price in items.items():
        tag = f" · {_('pack.label.' + labels[qty])}" if qty in labels else ""
        b.button(
            text=f"{qty} {unit} — {price_tag(price, sale_pct)}{tag}",
            callback_data=f"packqty:{pack}:{qty}",
        )
    b.button(text=_("btn.close"), callback_data="close")
    b.adjust(1)
    return b.as_markup()


def pack_gateway_keyboard(_: Translator, pack: str, qty: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for gw, label in GATEWAYS:
        b.button(text=label, callback_data=f"packpay:{gw}:{pack}:{qty}")
    b.button(text=_("btn.back"), callback_data=f"pack:{pack}")
    b.adjust(2, 2, 1)
    return b.as_markup()


def gateway_keyboard(_: Translator, product: str, months: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for gw, label in GATEWAYS:
        b.button(text=label, callback_data=f"pay:{gw}:{product}:{months}")
    b.button(text=_("btn.back"), callback_data=f"prem:{product}")
    b.adjust(2, 2, 1)
    return b.as_markup()
