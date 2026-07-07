"""Effective per-service generation options = the code spec narrowed/extended by
the admin's ``service_options`` override, with the money-guard applied ONCE here.

Single source of truth for every surface that renders a service's option buttons —
the bot config keyboards (``photo_config`` / ``video_config``) and the Mini App
effect card (``api.routers.miniapp._model_card``) — so the admin's option lists and
hidden toggles apply identically everywhere instead of each surface re-deriving them.

Money-guard: option lists whose VALUE feeds a cost map (``models``, ``qualities``,
``durations``, ``resolutions``) may only be narrowed / reordered / relabelled to
values the code already prices — an admin can't introduce an unpriced value (e.g.
"8k", 20s) that would fall through the cost map and undercharge. Cost-neutral lists
(``ratios`` cost-the-same, ``counts`` charged linearly per×count) are free to extend.
Structural toggles named in ``hide`` (audio/fourk/seed/enhance/modes) are removed.
``modes`` keep the code order (cost-affecting, never narrowed) but are hideable.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EffectiveOptions:
    models: list[tuple[str, str]] = field(default_factory=list)
    qualities: list[str] = field(default_factory=list)
    ratios: list[str] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)
    durations: list[int] = field(default_factory=list)
    resolutions: list[str] = field(default_factory=list)
    modes: list[tuple[str, str]] = field(default_factory=list)
    hide: frozenset[str] = frozenset()


def _guard_pairs(override, spec_pairs):
    """(value,label) list narrowed to values the code prices; empty override or an
    all-unknown override falls back to the full spec list."""
    spec_vals = {v for v, _ in spec_pairs}
    chosen = [(v, lbl) for v, lbl in (override or spec_pairs) if v in spec_vals]
    return chosen or list(spec_pairs)


def _guard_list(override, spec_list):
    allowed = set(spec_list)
    chosen = [x for x in (override or spec_list) if x in allowed]
    return chosen or list(spec_list)


def effective_options(spec, override: dict | None) -> EffectiveOptions:
    """Resolve the option lists actually shown for ``spec`` given the admin
    ``override`` (a sanitized entry from ``pricing.service_options``)."""
    o = override or {}
    eff = EffectiveOptions(hide=frozenset(o.get("hide") or []))
    # Cost-affecting → guarded to priced values.
    if getattr(spec, "models", None):
        eff.models = _guard_pairs(o.get("models"), spec.models)
    if getattr(spec, "qualities", None):
        eff.qualities = _guard_list(o.get("qualities"), spec.qualities)
    if getattr(spec, "durations", None):
        eff.durations = _guard_list(o.get("durations"), spec.durations)
    if getattr(spec, "resolutions", None):
        eff.resolutions = _guard_list(o.get("resolutions"), spec.resolutions)
    # Cost-neutral → admin list wins as-is (free to extend), else the spec's.
    if getattr(spec, "ratios", None) or o.get("ratios"):
        eff.ratios = list(o.get("ratios") or getattr(spec, "ratios", []))
    if getattr(spec, "counts", None) or o.get("counts"):
        eff.counts = list(o.get("counts") or getattr(spec, "counts", []))
    # Modes are cost-affecting (grok edit costs 2) → never narrowed; keep code
    # order, hideable via the "modes" token.
    if getattr(spec, "modes", None):
        eff.modes = list(spec.modes)
    return eff
