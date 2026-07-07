"""Render a video service sub-menu keyboard from a VideoSpec + FSM config."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.ai_router.video_specs import VideoSpec
from core.i18n import Translator
from core.services.service_config import effective_options


def _append_rows(layout: list[int], count: int, width: int = 8) -> None:
    """Append row widths for ``count`` buttons so no row exceeds Telegram's 8-per-row
    cap — aiogram's ``adjust()`` raises ValueError above 8. Admin-extendable lists
    (cost-neutral ratios) can hold more than 8 entries; groups of ≤8 stay a single row."""
    for i in range(0, count, width):
        layout.append(min(width, count - i))


def video_config_kb(
    _: Translator, spec: VideoSpec, cfg: dict, doc_links: dict[str, str] | None = None,
    options: dict | None = None,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    layout: list[int] = []
    # The admin's option lists + money-guard live in one shared resolver so the bot
    # keyboard and the Mini App effect card show identical options.
    eff = effective_options(spec, options)
    models = eff.models
    durations = eff.durations
    resolutions = eff.resolutions
    ratios = eff.ratios
    hidden = eff.hide   # structural toggles the admin hid

    def mark(field: str, value) -> str:
        return "✅ " if str(cfg.get(field)) == str(value) else ""

    if spec.modes and "modes" not in hidden:
        for v, label in spec.modes:
            # Localize known mode labels (spec.mode.<value>); fall back to the spec's
            # own label for any value without a translation key.
            mkey = f"spec.mode.{v}"
            mlabel = _(mkey)
            if mlabel == mkey:
                mlabel = label
            b.button(text=f"{mark('mode', v)}{mlabel}", callback_data=f"vcfg:mode:{v}")
        layout.append(len(spec.modes))
    if models:
        for v, label in models:
            b.button(text=f"{mark('model', v)}{label}", callback_data=f"vcfg:model:{v}")
        _append_rows(layout, len(models))
    if durations:
        sec = _("unit.sec")
        for d in durations:
            b.button(text=f"{mark('duration', d)}{d} {sec}", callback_data=f"vcfg:duration:{d}")
        layout.append(len(durations))
    if resolutions:
        for r in resolutions:
            b.button(text=f"{mark('res', r)}{r}", callback_data=f"vcfg:res:{r}")
        layout.append(len(resolutions))
    if ratios:
        for r in ratios:
            b.button(text=f"{mark('ratio', r)}{r}", callback_data=f"vcfg:ratio:{r}")
        _append_rows(layout, len(ratios))
    if spec.audio and "audio" not in hidden:
        on = "✅ " if cfg.get("audio") else ""
        b.button(text=f"{on}{_('vcfg.with_sound')}", callback_data="vcfg:audio:toggle")
        layout.append(1)
    if spec.fourk and "fourk" not in hidden:
        on = "✅ " if cfg.get("fourk") else ""
        b.button(text=f"{on}4K", callback_data="vcfg:fourk:toggle")
        layout.append(1)
    if spec.prompt_enhance and "enhance" not in hidden:
        on = "✅ " if cfg.get("enhance") else ""
        b.button(text=f"{on}{_('vcfg.enhance')}", callback_data="vcfg:enhance:toggle")
        layout.append(1)
    if spec.seed and "seed" not in hidden:
        seed_label = _("vcfg.seed_set", v=cfg["seed"]) if cfg.get("seed") else _("vcfg.seed_add")
        b.button(text=seed_label, callback_data="vcfg:seed:ask")
        layout.append(1)
    links = doc_links or {}
    if spec.doc_link_key and links.get(spec.doc_link_key):
        b.button(text=_("btn.instruction"), url=links[spec.doc_link_key])
        layout.append(1)

    b.button(text=_("btn.back"), callback_data="video:back")
    layout.append(1)
    b.adjust(*layout)
    return b.as_markup()


def topup_video_kb(_: Translator) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("btn.topup_pay"), callback_data="pack:video_pack")]
        ]
    )
