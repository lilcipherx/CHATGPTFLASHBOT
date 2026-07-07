"""Per-service video config specs (§21A) — drive the sub-menu keyboards and the
generation cost (charged against the video pack). All video services are async:
the handler creates a generation_job and an ARQ worker submits/polls/delivers."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class VideoSpec:
    key: str
    title: str
    description: str
    pack: str = "video"          # which pack to charge ("video" | "image" for MJ Video)
    models: list[tuple[str, str]] = field(default_factory=list)
    durations: list[int] = field(default_factory=list)        # seconds
    resolutions: list[str] = field(default_factory=list)
    ratios: list[str] = field(default_factory=list)
    modes: list[tuple[str, str]] = field(default_factory=list)  # grok create/edit
    audio: bool = False
    fourk: bool = False          # show a 4K toggle (Veo/Kling, §21A)
    image_input: bool = False    # accepts a photo as the first frame / base
    seed: bool = False
    prompt_enhance: bool = False
    doc_link_key: str | None = None
    cost: Callable[[dict], int] = lambda cfg: 1
    default: dict = field(default_factory=dict)


def _kling_cost(cfg: dict) -> int:
    # §22 — 5s=1, 10s=2, 15s=3; 4K ×2
    base = {5: 1, 10: 2, 15: 3}.get(int(cfg.get("duration", 5)), 1)
    return base * 2 if cfg.get("fourk") else base


def _veo_cost(cfg: dict) -> int:
    return 2 if cfg.get("fourk") else 1


def _grok_cost(cfg: dict) -> int:
    return 2 if cfg.get("mode") == "edit" else 1


def _pika_cost(cfg: dict) -> int:
    # §22 — 5/720=1 … 10/1080=3
    base = 1 if int(cfg.get("duration", 5)) == 5 else 2
    return base + (1 if cfg.get("res") == "1080p" else 0)


VIDEO_SPECS: dict[str, VideoSpec] = {
    "seedance": VideoSpec(
        key="seedance",
        title="📊 Seedance 2.0",
        description=(
            "Генерация видео по тексту, изображениям, видео и аудио.\n\n"
            "Задайте параметры и отправьте промпт для запуска ⚡"
        ),
        models=[("fast", "Fast"), ("standard", "Standard")],
        durations=[4, 8, 12, 15],
        resolutions=["480p", "720p"],
        ratios=["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"],
        audio=True,
        image_input=True,
        cost=lambda cfg: 1,
        default={"model": "fast", "duration": 4, "res": "480p", "ratio": "16:9", "audio": True},
    ),
    "veo": VideoSpec(
        key="veo",
        title="🌿 Veo 3.1",
        description="Veo 3.1 — кинематографичное видео от Google. Отправьте промпт ⚡",
        models=[("veo_3_1", "VEO 3.1"), ("veo_3_1_fast", "VEO 3.1 FAST")],
        ratios=["16:9", "9:16"],
        fourk=True,
        image_input=True,
        seed=True,
        doc_link_key="veo",
        cost=_veo_cost,
        default={"model": "veo_3_1_fast", "ratio": "16:9"},
    ),
    "grok": VideoSpec(
        key="grok",
        title="⚡ Grok Imagine",
        description=(
            "Создание и редактирование видео. Редактор расходует 2 генерации.\n"
            "Запрещены 18+, насилие и дипфейки. Отправьте промпт ⚡"
        ),
        modes=[("create", "Создать"), ("edit", "Редактор")],
        ratios=["auto", "1:1", "9:16", "16:9", "4:3", "3:4"],
        durations=[6, 9, 12, 15],
        cost=_grok_cost,
        default={"mode": "create", "ratio": "auto", "duration": 6},
    ),
    "kling_ai": VideoSpec(
        key="kling_ai",
        title="✨ Kling AI",
        description="Создание и редактирование видео. Отправьте промпт ⚡",
        # FIX: AI-9 - real Kling model IDs (was: "3.0", "o1", "2.6", "2.5t" which are
        # fictional and caused every Kling job to 400 with model_not_found). The
        # kling adapter (video_adapters.py) maps these to the real API values.
        models=[
            ("kling-v1", "Kling V1"),
            ("kling-v2-master", "Kling V2 Master"),
        ],
        durations=[5, 10],
        ratios=["1:1", "16:9", "9:16"],
        audio=True,
        fourk=True,
        image_input=True,
        cost=_kling_cost,
        default={"model": "kling-v1", "duration": 5, "ratio": "16:9", "audio": True},
    ),
    "hailuo": VideoSpec(
        key="hailuo",
        title="🎭 Minimax Hailuo",
        description="Hailuo — видео по описанию и изображению. Отправьте промпт ⚡",
        models=[("fast", "Hailuo 2.3 Fast"), ("2.3", "Hailuo 2.3"), ("02", "Hailuo 02")],
        durations=[5, 10],
        resolutions=["768P", "1080P"],
        prompt_enhance=True,
        image_input=True,
        cost=lambda cfg: 1,
        default={"model": "fast", "duration": 5, "res": "768P", "enhance": True},
    ),
    "pika": VideoSpec(
        key="pika",
        title="☁ Pika 2.5",
        description="Pika Labs — видео по описанию и изображениям. Отправьте промпт ⚡",
        durations=[5, 10],
        resolutions=["720p", "1080p"],
        ratios=["1:1", "16:9", "9:16"],
        image_input=True,
        cost=_pika_cost,
        default={"duration": 5, "res": "720p", "ratio": "1:1"},
    ),
    "mj_video": VideoSpec(
        key="mj_video",
        title="🎨 Midjourney Video",
        description=(
            "Midjourney Video — анимация изображений. Отправьте фото и/или промпт ⚡\n"
            "Списывается из пакета изображений."
        ),
        pack="image",  # §26C — MJ Video draws on the image pack
        image_input=True,
        doc_link_key="midjourney",
        cost=lambda cfg: 1,
        default={},
    ),
}
