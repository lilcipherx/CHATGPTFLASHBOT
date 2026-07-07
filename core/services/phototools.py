"""Фото-инструменты (ТЗ §5): Face Swap / Upscale / Аватары — чистый сервисный слой.

Здесь живёт provider-agnostic ядро: реестр инструментов (ключ, RU-название, цена в
🪙) и единая точка входа ``run(tool, image_url, **opts)``, которая диспатчит вызов на
адаптер провайдера. Пока реальный провайдер/ключ не настроен, ``run`` возвращает
типизированный ``ToolResult(ok=False, reason="provider_unavailable")`` ВМЕСТО
исключения — это делает модуль безопасным для деплоя до подключения UI бота
(человек довяжет хендлеры позже).

Цена каждого инструмента берётся из live-конфига через core.services.pricing
(см. блок ``phototools`` в pricing.defaults() — добавляется отдельно, см. wiring
notes). Если live-конфиг недоступен, используется захардкоженный дефолт из реестра.

Зависимостей от Redis/сети на уровне импорта НЕТ: провайдеры обращаются к сети
только когда настроен соответствующий API-ключ (см. is_available()).
"""
from __future__ import annotations

import enum
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings


class PhotoTool(enum.StrEnum):
    """Поддерживаемые фото-инструменты (ТЗ §5). Значение = стабильный ключ,
    используемый в конфиге цен и в callback_data бота."""

    FACE_SWAP = "face_swap"
    UPSCALE = "upscale"
    AVATARS = "avatars"


@dataclass(frozen=True)
class ToolSpec:
    """Описание инструмента: ключ, RU-название и дефолтная цена в 🪙 (кредитах).

    ``default_price`` — fallback, когда live-конфиг (pricing) не содержит цену для
    этого ключа. Реальная цена для показа/списания берётся через price()."""

    tool: PhotoTool
    title: str
    default_price: int

    @property
    def key(self) -> str:
        return self.tool.value


@dataclass
class ToolResult:
    """Результат запуска инструмента (по образцу core.ai_router.base.*Result).

    ok=True  → ``url``/``data`` содержат итоговое изображение.
    ok=False → ``reason`` — машинно-читаемая причина (например
    ``"provider_unavailable"``), бот покажет понятное сообщение и вернёт списание.
    """

    ok: bool
    url: str | None = None
    data: bytes | None = None
    reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


# Машинно-читаемые причины отказа (для бота/локализации).
REASON_PROVIDER_UNAVAILABLE = "provider_unavailable"
REASON_UNKNOWN_TOOL = "unknown_tool"
REASON_BAD_INPUT = "bad_input"
REASON_PROVIDER_ERROR = "provider_error"


# ---- реестр инструментов ----------------------------------------------------
# RU-названия и дефолтные цены согласованы с существующей логикой §22A/§15A:
# Face Swap = 1 image-credit, Upscale = 2, пакет аватаров = 200 (AVATAR_PRICE).
REGISTRY: dict[PhotoTool, ToolSpec] = {
    PhotoTool.FACE_SWAP: ToolSpec(PhotoTool.FACE_SWAP, "🔄 Замена лица", 1),
    PhotoTool.UPSCALE: ToolSpec(PhotoTool.UPSCALE, "🔍 Улучшение качества", 2),
    PhotoTool.AVATARS: ToolSpec(PhotoTool.AVATARS, "🧑‍🎨 AI-аватары", 200),
}

# Ключ верхнего уровня в live-конфиге (pricing.defaults()), в котором админ задаёт
# цены инструментов: {"phototools": {"face_swap": 1, "upscale": 2, "avatars": 200}}.
CONFIG_KEY = "phototools"


def resolve(tool: PhotoTool | str) -> ToolSpec | None:
    """Найти ToolSpec по enum или по строковому ключу (None — неизвестный ключ)."""
    if isinstance(tool, PhotoTool):
        return REGISTRY.get(tool)
    try:
        return REGISTRY.get(PhotoTool(tool))
    except ValueError:
        return None


def all_specs() -> list[ToolSpec]:
    """Все инструменты (для построения меню в боте)."""
    return list(REGISTRY.values())


async def price(session: AsyncSession, tool: PhotoTool | str) -> int | None:
    """Цена инструмента в 🪙 из live-конфига (блок ``phototools``), с откатом на
    ``default_price`` реестра. Возвращает None для неизвестного инструмента.

    Читает конфиг через публичный accessor pricing.get_config (Redis-кэш +
    дефолты), pricing.py НЕ модифицируется."""
    spec = resolve(tool)
    if spec is None:
        return None
    # Локальный импорт, чтобы избежать цикла на уровне модуля и не тянуть pricing
    # при чистом импорте phototools.
    from core.services import pricing

    cfg = await pricing.get_config(session)
    block = cfg.get(CONFIG_KEY) or {}
    raw = block.get(spec.key, spec.default_price)
    try:
        val = int(raw)
    except (TypeError, ValueError):
        val = spec.default_price
    return max(0, val)


# ---- адаптеры провайдеров ---------------------------------------------------
# Адаптер = асинхронная функция (image_url, **opts) -> ToolResult. Реальный вызов
# провайдера должен происходить ТОЛЬКО когда настроен ключ; иначе вернуть
# ToolResult(ok=False, reason=REASON_PROVIDER_UNAVAILABLE).
Adapter = Callable[..., Awaitable[ToolResult]]


def _provider_key() -> str:
    """API-ключ провайдера фото-инструментов (Replicate-совместимый шлюз для
    face swap / upscale / avatars). Пустая строка = провайдер не настроен.

    Имя сеттинга: settings.replicate_api_key (добавляется в core.config —
    см. wiring notes). getattr с дефолтом '' оставляет модуль импортируемым даже
    до добавления сеттинга, поэтому тесты/импорт не падают."""
    return getattr(settings, "replicate_api_key", "") or ""


def provider_available() -> bool:
    """True, когда настроен ключ провайдера (иначе run() вернёт provider_unavailable)."""
    return bool(_provider_key())


async def _unavailable_adapter(image_url: str, **opts: Any) -> ToolResult:
    """Заглушка по умолчанию: провайдер ещё не реализован/не настроен."""
    return ToolResult(ok=False, reason=REASON_PROVIDER_UNAVAILABLE)


# tool -> адаптер. Пока ни один реальный провайдер не подключён: все указывают на
# заглушку, которая честно сообщает «недоступно» (по образцу
# core.ai_router.image_adapters._UnavailableImage). Реальные адаптеры
# подменяются здесь, когда подтверждены модели/эндпоинты провайдера (ТЗ §7).
_ADAPTERS: dict[PhotoTool, Adapter] = {
    PhotoTool.FACE_SWAP: _unavailable_adapter,
    PhotoTool.UPSCALE: _unavailable_adapter,
    PhotoTool.AVATARS: _unavailable_adapter,
}


async def run(tool: PhotoTool | str, image_url: str, **opts: Any) -> ToolResult:
    """Запустить фото-инструмент над ``image_url`` и вернуть ToolResult.

    Контракт:
    * неизвестный инструмент → ok=False, reason=unknown_tool;
    * пустой image_url       → ok=False, reason=bad_input;
    * нет ключа провайдера   → RAISES ProviderUnavailable (FIX: F28 - was soft-fail,
      but workers expect an exception so they refund + notify; mirrors ai_router
      adapters). Catch ProviderUnavailable in the caller if a soft-fail is needed.
    * ошибка провайдера      → ok=False, reason=provider_error.

    ``opts`` пробрасываются в адаптер (например target_url для face_swap,
    factor='x2'/'x4' для upscale, count для avatars)."""
    spec = resolve(tool)
    if spec is None:
        return ToolResult(ok=False, reason=REASON_UNKNOWN_TOOL)
    if not image_url:
        return ToolResult(ok=False, reason=REASON_BAD_INPUT)
    if not provider_available():
        # FIX: H6 - raise immediately so the caller (worker) treats this as a provider
        # failure and refunds + notifies, rather than going through _unavailable_adapter
        # which silently returns ToolResult(ok=False). Either path is safe, but raising
        # is the contract the workers expect (mirrors core.ai_router adapters).
        from core.ai_router.base import ProviderUnavailable
        raise ProviderUnavailable(spec.tool)
    adapter = _ADAPTERS.get(spec.tool, _unavailable_adapter)
    try:
        return await adapter(image_url, **opts)
    except Exception:  # noqa: BLE001 — любую ошибку провайдера превращаем в мягкий отказ
        return ToolResult(ok=False, reason=REASON_PROVIDER_ERROR)
