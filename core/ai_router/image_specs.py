"""Per-service image config specs (§21B) — drive the sub-menu keyboards, the
generation cost, and which budget is charged (weekly quota vs image pack).

`pack=None` means the service draws on the weekly text/image quota (GPT Image 2,
Nano Banana 2) and is NOT deducted from the image pack (§10.2)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServiceSpec:
    key: str
    title: str
    description: str
    pack: str | None                       # "image" | None(weekly)
    models: list[tuple[str, str]] = field(default_factory=list)   # (value, label)
    qualities: list[str] = field(default_factory=list)
    ratios: list[str] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)               # output image count
    seed: bool = False
    input_limit: int = 1
    doc_link_key: str | None = None
    text_only: bool = False
    # cost(config) -> generations to charge (against `pack` or weekly)
    cost: Callable[[dict], int] = lambda cfg: 1
    default: dict = field(default_factory=dict)


RATIOS_5 = ["1:1", "9:16", "16:9", "3:4", "4:3"]


def _nano_cost(cfg: dict) -> int:
    # §15A.1 — 1k=2, 2k=3, 4k=4 (applies to both NB2 weekly and NBPro pack)
    return {"1k": 2, "2k": 3, "4k": 4}.get(cfg.get("quality", "1k"), 2)


def _flux_cost(cfg: dict) -> int:
    # §15A.1 — Flex and Max cost 2; FLUX 2 / Pro cost 1
    return 2 if cfg.get("model") in {"flux2_flex", "flux2_max"} else 1


PHOTO_SPECS: dict[str, ServiceSpec] = {
    "gpt_image2": ServiceSpec(
        key="gpt_image2",
        title="🖼 GPT Image 2",
        description=(
            "Создавайте и редактируйте изображения прямо в чате.\n\n"
            "Готовы начать?\nОтправьте от 1 до 4 изображений, которые вы хотите "
            "изменить, или напишите в чат, что нужно создать"
        ),
        pack=None,  # weekly quota, NOT image pack
        ratios=RATIOS_5,
        counts=[1, 2, 3, 4],
        input_limit=4,
        doc_link_key="gpt_images",
        cost=lambda cfg: 1,
        default={"ratio": "1:1", "count": 1},
    ),
    "nano_banana": ServiceSpec(
        key="nano_banana",
        title="🍌 Nano Banana Pro",
        description=(
            "Gemini Images — Ещё ярче. Ещё умнее!\n\n"
            "Создавайте и редактируйте изображения прямо в чате. Отправьте от 1 "
            "до 10 изображений или напишите, что нужно создать."
        ),
        pack=None,  # NB2 weekly; NBPro switches to image pack (handled in flow)
        models=[("nb2", "Nano Banana 2"), ("nbpro", "Nano Banana Pro")],
        qualities=["1k", "2k", "4k"],
        counts=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        input_limit=10,
        doc_link_key="banana",
        cost=_nano_cost,
        default={"model": "nb2", "quality": "1k", "count": 1},
    ),
    "seedream": ServiceSpec(
        key="seedream",
        title="🌱 Seedream 5",
        description=(
            "Создавайте и редактируйте изображения прямо в чате. Отправьте от 1 "
            "до 10 изображений или напишите, что нужно создать."
        ),
        pack="image",
        models=[("seedream_4_5", "Seedream 4.5"), ("seedream_5", "Seedream 5")],
        qualities=["2k", "3k", "4k"],
        ratios=RATIOS_5,
        input_limit=10,
        cost=lambda cfg: 1,
        default={"model": "seedream_5", "quality": "2k", "ratio": "1:1"},
    ),
    "midjourney": ServiceSpec(
        key="midjourney",
        title="🎨 Midjourney",
        description=(
            "Напишите в чат, какое изображение вы хотите создать.\n\nБот "
            "поддерживает все основные параметры и возможности Midjourney."
        ),
        pack="image",
        models=[("v7", "V7"), ("v8_1", "V8.1")],
        text_only=True,
        doc_link_key="midjourney",
        cost=lambda cfg: 1,
        default={"model": "v8_1"},
    ),
    "flux2": ServiceSpec(
        key="flux2",
        title="✏️ FLUX 2",
        description=(
            "Выберите соотношение сторон и модель Flux. Модели Flex и Max "
            "расходуют 2 генерации.\n\nДля запуска генерации напишите в чат, "
            "какое изображение вы хотите создать 🐝"
        ),
        pack="image",
        models=[
            ("flux2", "FLUX 2"),
            ("flux2_flex", "FLUX 2 Flex"),
            ("flux2_pro", "FLUX 2 Pro"),
            ("flux2_max", "FLUX 2 Max"),
        ],
        ratios=RATIOS_5,
        seed=True,
        cost=_flux_cost,
        default={"model": "flux2", "ratio": "1:1"},
    ),
    "recraft": ServiceSpec(
        key="recraft",
        title="🎯 Recraft",
        description=(
            "Recraft — векторная графика и дизайн. Напишите в чат, какое "
            "изображение вы хотите создать."
        ),
        pack="image",
        ratios=RATIOS_5,
        cost=lambda cfg: 1,
        default={"ratio": "1:1"},
    ),
}
