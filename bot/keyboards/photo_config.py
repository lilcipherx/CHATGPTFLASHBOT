"""Render a service sub-menu keyboard from an ImageSpec + current FSM config.

Callback scheme: pcfg:<field>:<value> toggles a config field; the prompt itself
is sent as a chat message while in PhotoSG.service_config."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.ai_router.image_specs import ServiceSpec
from core.i18n import Translator
from core.services.service_config import effective_options


def _append_rows(layout: list[int], count: int, width: int = 8) -> None:
    """Append row widths for ``count`` buttons so no row exceeds Telegram's 8-per-row
    cap — aiogram's ``adjust()`` raises ValueError above 8. Admin-extendable lists
    (cost-neutral ratios) can hold more than 8 entries; groups of ≤8 stay a single row."""
    for i in range(0, count, width):
        layout.append(min(width, count - i))


def service_config_kb(
    _: Translator, spec: ServiceSpec, cfg: dict, doc_links: dict[str, str] | None = None,
    options: dict | None = None,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    layout: list[int] = []
    # The admin's option lists + money-guard live in one shared resolver so the bot
    # keyboard and the Mini App effect card show identical options.
    eff = effective_options(spec, options)
    models = eff.models
    qualities = eff.qualities
    ratios = eff.ratios
    counts = eff.counts
    hidden = eff.hide   # structural toggles the admin hid

    def mark(field: str, value: str) -> str:
        return "✅ " if str(cfg.get(field)) == str(value) else ""

    if models:
        for value, label in models:
            b.button(text=f"{mark('model', value)}{label}", callback_data=f"pcfg:model:{value}")
        _append_rows(layout, len(models))
    if qualities:
        for q in qualities:
            b.button(text=f"{mark('quality', q)}{q}", callback_data=f"pcfg:quality:{q}")
        _append_rows(layout, len(qualities))
    if ratios:
        for r in ratios:
            b.button(text=f"{mark('ratio', r)}{r}", callback_data=f"pcfg:ratio:{r}")
        _append_rows(layout, len(ratios))
    if counts:
        for n in counts:
            b.button(text=f"{mark('count', str(n))}{n}", callback_data=f"pcfg:count:{n}")
        # up to 5 per row
        remaining = len(counts)
        while remaining > 0:
            layout.append(min(5, remaining))
            remaining -= 5
    if spec.seed and "seed" not in hidden:
        seed_label = _("vcfg.seed_set", v=cfg["seed"]) if cfg.get("seed") else _("vcfg.seed_add")
        b.button(text=seed_label, callback_data="pcfg:seed:ask")
        layout.append(1)
    links = doc_links or {}
    if spec.doc_link_key and links.get(spec.doc_link_key):
        b.button(text=_("btn.instruction"), url=links[spec.doc_link_key])
        layout.append(1)

    b.button(text=_("btn.back"), callback_data="photo:back")
    layout.append(1)
    b.adjust(*layout)
    return b.as_markup()


def topup_image_kb(_: Translator) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("btn.topup_pay"), callback_data="pack:image_pack")]
        ]
    )
