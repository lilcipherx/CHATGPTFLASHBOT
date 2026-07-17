"""Live business configuration — prices & limits editable from the admin panel
without a redeploy (ТЗ §1, the foundation).

Overrides live in the `pricing` KV table under the key ``business_config`` and are
deep-merged over the static defaults in core.constants / core.config, then cached
in Redis for a few seconds (same pattern as feature_flags / provider_keys). This is
the single source of truth every price/limit read should funnel through, replacing
direct reads of ``constants.SUBSCRIPTION_PRICES`` / ``settings.free_text_weekly`` so
an admin change applies live. Consumers (quota, payments, keyboards, Mini App) are
wired to it incrementally — see ТЗ roadmap.

JSON round-trips turn integer map keys into strings (qty/months), so the getters
accept both str and int keys.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.constants import (
    AVATAR_PRICE,
    CREDIT_PACKS,
    PACK_PRICES,
    SUBSCRIPTION_PRICES,
)
from core.models import Pricing
from core.redis_client import redis_client

KEY = "business_config"
_CACHE_KEY = "cache:business_config"
_CACHE_TTL = 10  # seconds


def defaults() -> dict[str, Any]:
    """Static defaults from constants / settings (the current hard-coded values)."""
    return {
        "limits": {
            "free_text_weekly": settings.free_text_weekly,
            "free_miniapp_weekly": settings.free_miniapp_weekly,
            "premium_daily": settings.premium_daily,
            "premium_x2_daily": settings.premium_x2_daily,
        },
        # Map keys are stringified so defaults and JSON-stored overrides share one
        # key type (JSON has no int keys), letting deep-merge apply partial overrides.
        "subscription_prices": {
            p: {str(m): s for m, s in months.items()}
            for p, months in SUBSCRIPTION_PRICES.items()
        },
        "pack_prices": {
            p: {str(q): s for q, s in qtys.items()} for p, qtys in PACK_PRICES.items()
        },
        "credit_packs": {str(q): s for q, s in CREDIT_PACKS.items()},
        "avatar_price": AVATAR_PRICE,
        # Promo mechanics (ТЗ §4 monetization) — all 0 = off, admin-configurable.
        "promos": {
            "welcome_bonus": 0,        # 🪙 granted once on first /start (new user)
            "first_purchase_bonus": 0,  # 🪙 granted on the user's first paid purchase
            "cashback_percent": 0,      # % of a 🪙 top-up returned as bonus 🪙
        },
        # Time-limited sale (ТЗ §4): a global discount applied to every price below
        # while active. percent 0 = off. The sale only counts inside the optional
        # window [from .. until] (both ISO datetimes, UTC): "from" lets an admin
        # schedule it ahead (null = active immediately), "until" is the end (null =
        # no expiry while percent > 0).
        "sale": {"percent": 0, "from": None, "until": None},
        # VIP / loyalty levels (ТЗ §4): auto-assigned by cumulative spend (in Stars-
        # equivalent). Each tier grants extra daily/weekly generation allowance.
        # enabled=False (default) = inert. Tiers are matched by the highest min_spent
        # the user has reached.
        "vip": {
            "enabled": False,
            "tiers": [
                {"name": "Bronze", "min_spent": 0, "bonus_daily": 0, "bonus_weekly": 0},
                {"name": "Silver", "min_spent": 2000, "bonus_daily": 20, "bonus_weekly": 50},
                {"name": "Gold", "min_spent": 5000, "bonus_daily": 50, "bonus_weekly": 150},
            ],
        },
        # Custom inline buttons (ТЗ §8 «конструктор кнопок»): admin-defined link
        # buttons shown by the /links bot command. Each = {text, url}. Empty = none.
        "custom_buttons": [],
        # Result retention (ТЗ §5 «срок хранения»): days to keep generated artifacts
        # before the daily cleanup cron prunes the DB rows AND their stored media. 0 =
        # keep forever. Prod defaults bound table/storage growth automatically; admin can
        # raise/lower or set 0 (keep forever) live in Pricing→Лимиты.
        "retention": {"job_days": 90, "gallery_days": 180},
        # Фото-инструменты (ТЗ §5): цены в 🪙 за инструмент, admin-editable.
        # face_swap/upscale/avatars — для реестра phototools; upscale_x2/x4 —
        # фактические тарифы апскейла, которые читает бот (bot/handlers/photo.py).
        "phototools": {
            "face_swap": 1, "upscale": 2, "avatars": 200,
            "upscale_x2": 2, "upscale_x4": 4,
        },
        # Документы (ТЗ §5): стоимость одного запроса к документу в генерациях,
        # admin-editable. On/off — через feature_flags["documents"].
        "documents": {"cost": 3},
        # Интернет-поиск /s /search (ТЗ §3): системный промпт, редактируемый из
        # админки («улучшить поиск»). Пусто → дефолтный промпт.
        "search": {
            "system_prompt": (
                "Ты ассистент с доступом к актуальной информации из интернета. "
                "Дай развёрнутый, точный и свежий ответ на запрос пользователя."
            ),
        },
        # Ads for free users (ТЗ §6): Premium is ad-free. enabled=False by default.
        "ads": {
            "enabled": False,
            "every_n": 5,   # append an ad after every Nth free-user reply
            "text": "✨ Оформите Premium, чтобы убрать рекламу и поднять лимиты.",
        },
        # Branding / welcome media (ТЗ §1/§3): optional media shown in /start.
        "branding": {
            "start_media_url": "",          # photo/video URL ("" = text-only /start)
            "start_media_type": "photo",    # photo | video
        },
        # Chat behaviour (ТЗ §3), admin-tunable live.
        "chat": {
            "memory_pairs": 5,         # rolling Q&A pairs kept as context (5–10)
            "markdown_enabled": True,  # render AI replies as safe Telegram Markdown
            "groups_enabled": True,    # respond in group chats (when mentioned/replied)
            "streaming_enabled": True,  # stream AI replies via progressive edits (ChatGPT-style)
        },
        # Generation knobs (ТЗ §5), admin-tunable.
        "generation": {
            "image_variants": 1,       # number of image variants to offer (1–4)
        },
        # Referral anti-fraud (ТЗ §6): withhold a referrer's reward until the
        # referred account is at least N hours old (combats instant fake-account
        # farming). enabled=False = off; min_referred_age_hours=0 = no age gate.
        "referral_fraud": {"enabled": False, "min_referred_age_hours": 24},
        # Maintenance mode (ТЗ §8/§9): when enabled, non-admin users get the message
        # and the bot stops processing their updates. Admins always pass through.
        "maintenance": {
            "enabled": False,
            "message": "🛠 Ведутся технические работы, скоро вернёмся.",
        },
        # Menu sections the bot exposes. The full product ships with every section
        # ON: images / video / music / search / documents are all live. Each section
        # actually generates as soon as its provider key is set on the admin
        # API-keys page (until then a generation attempt safely refunds — money is
        # never lost). The admin can still turn a section OFF individually (e.g. a
        # provider outage), which shows its editable "coming soon" text instead.
        # Chat/model itself is always available and is not listed here.
        "sections": {
            "images": {
                "enabled": True,
                "soon": "🎨 Раздел изображений скоро будет — уже готовим. "
                        "Пока доступен умный чат: просто напишите сообщение.",
            },
            "video": {
                "enabled": True,
                "soon": "🎬 Генерация видео скоро. Мы её подключаем — "
                        "следите за обновлениями. Пока доступен умный чат.",
            },
            "music": {
                "enabled": True,
                "soon": "🎵 Генерация музыки скоро. Готовим для вас. "
                        "Пока доступен умный чат.",
            },
            # Documents works on the chat model (no media provider). Premium-only
            # (the upload handler gates on user.is_premium).
            "documents": {
                "enabled": True,
                "soon": "📄 Работа с документами скоро. Пока доступен умный чат.",
            },
            "search": {
                "enabled": True,
                "soon": "🔍 Поиск в интернете скоро. Пока доступен умный чат.",
            },
        },
        # Mini App effect segments (photo/video) visibility (ТЗ §13). Hybrid: "auto"
        # shows the segment only when a working provider exists for that modality (a
        # direct env-key adapter OR a configured Kie/MuAPI aggregator account) so the
        # storefront never offers an effect that can only refund; "on"/"off" force it.
        "miniapp_sections": {"photo": "auto", "video": "auto"},
        # Sponsored (is_ad) effects are FREE for the user up to this many generations
        # per UTC day (the sponsor pays); past the cap the user pays as usual. 0 = no
        # free sponsored generations (the effect is just badged/promoted).
        "sponsored_free_daily": 3,
        # Premium queue priority (ТЗ §8): when enabled, generation jobs from Premium
        # users jump ahead of free users' jobs in the ARQ queue. On by default.
        "queue": {"premium_priority_enabled": True},
        # Auto-notifications / engagement (ТЗ §7), admin-tunable. Each channel has an
        # on/off + threshold; the scheduler reads this live.
        "notifications": {
            "premium_expiry_enabled": True,
            "premium_expiry_days_before": 3,   # warn N days before Premium ends
            "low_balance_enabled": True,
            "low_balance_threshold": 5,         # warn when ✨ balance drops to/below this
            "winback_enabled": True,
            "winback_inactive_days": 14,        # nudge users inactive for N days
            # Remind users with a live daily-bonus streak that today's bonus is ready
            # (claimed yesterday, not yet today) so they don't break the streak.
            "bonus_available_enabled": True,
            # Abandoned-cart (ТЗ §7): nudge users who reached the pay step but didn't
            # pay, after the cart has sat open this many hours. Off by default.
            "abandoned_cart_enabled": False,
            "abandoned_cart_after_hours": 1,
        },
        # Preset roles / personas (ТЗ §3): a curated list the user can pick in /roles,
        # admin-editable. Each = {key, title, prompt, desc}. The prompt becomes the
        # user's custom system role; desc is a 1-line preview shown in /roles. Empty
        # list = feature shows nothing (still safe).
        "preset_roles": [
            {"key": "tutor", "title": "👩‍🏫 Репетитор",
             "desc": "Объясняет пошагово и проверяет понимание",
             "prompt": "Ты терпеливый преподаватель. Объясняй пошагово, простыми словами, "
                       "с примерами, и проверяй понимание короткими вопросами."},
            {"key": "coder", "title": "👨‍💻 Программист",
             "desc": "Рабочий код + подводные камни и best practices",
             "prompt": "Ты senior-разработчик. Давай рабочий код с краткими пояснениями, "
                       "указывай на подводные камни и лучшие практики."},
            {"key": "copywriter", "title": "✍️ Копирайтер",
             "desc": "Живой, убедительный текст под аудиторию",
             "prompt": "Ты профессиональный копирайтер. Пиши живо, структурно и убедительно, "
                       "адаптируя тон под аудиторию."},
            {"key": "psychologist", "title": "🧘 Психолог",
             "desc": "Эмпатичная поддержка без осуждения",
             "prompt": "Ты эмпатичный собеседник-психолог. Поддерживай, задавай уточняющие "
                       "вопросы, не осуждай. Не давай медицинских диагнозов."},
            {"key": "translator", "title": "🌐 Переводчик",
             "desc": "Точный и естественный перевод с нюансами",
             "prompt": "Ты профессиональный переводчик. Переводи точно и естественно, "
                       "сохраняя смысл, тон и стиль оригинала; при необходимости поясняй нюансы."},
            {"key": "marketer", "title": "📈 Маркетолог",
             "desc": "Идеи, заголовки и структура под результат",
             "prompt": "Ты опытный маркетолог. Предлагай практичные идеи, цепляющие заголовки и "
                       "чёткую структуру, опирайся на целевую аудиторию и измеримый результат."},
            {"key": "lawyer", "title": "⚖️ Юрист",
             "desc": "Понятные пояснения и предупреждение о рисках",
             "prompt": "Ты юридический консультант. Объясняй понятным языком, ссылайся на общие "
                       "принципы права и предупреждай о рисках. Не заменяешь очную консультацию."},
            {"key": "chef", "title": "🍳 Кулинар",
             "desc": "Рецепты с точными пропорциями и заменами",
             "prompt": "Ты шеф-повар. Давай рецепты с точными пропорциями, шагами и заменами "
                       "ингредиентов, советы по технике и подаче."},
        ],
        # "Инструкция" links shown under photo/video service configs, admin-editable
        # (ТЗ §8). Keyed by service doc_link_key (DOC_LINK_KEYS). Empty by default —
        # the button appears only for a key with a non-empty URL set here, so no
        # third-party links ship out of the box.
        "doc_links": {},
        # Per-service generation option BUTTONS, admin-editable (ТЗ §5/§8). Keyed by
        # service key (gpt_image2, kling_ai, …); each may override the option lists the
        # config sub-menu shows: qualities/ratios/resolutions (strings), counts/
        # durations (ints), models ([value,label] pairs). Empty = use the code default
        # from the service spec. Only the BUTTONS change — costs/flow stay in code.
        "service_options": {},
    }


def _merge(base: dict, over: dict) -> dict:
    """Recursively deep-merge ``over`` onto ``base`` so a partial override at any
    nesting level (e.g. one month's price) keeps the sibling defaults."""
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


async def _load_overrides(session: AsyncSession) -> dict:
    row = await session.get(Pricing, KEY)
    return dict(row.value or {}) if row else {}


async def get_config(session: AsyncSession) -> dict[str, Any]:
    """Full merged business config (defaults <- DB overrides), Redis-cached."""
    try:
        raw = await redis_client.get(_CACHE_KEY)
        if raw:
            return json.loads(raw)
    except Exception:  # noqa: BLE001 — cache is best-effort
        pass
    try:
        overrides = await _load_overrides(session)
    except Exception:  # noqa: BLE001 — pricing table absent (pre-migration) -> defaults
        overrides = {}
    cfg = _merge(defaults(), overrides)
    try:
        await redis_client.set(_CACHE_KEY, json.dumps(cfg), ex=_CACHE_TTL)
    except Exception:  # noqa: BLE001
        pass
    return cfg


async def set_config(session: AsyncSession, patch: dict[str, Any]) -> dict[str, Any]:
    """Apply a partial override (deep-merged) and invalidate the cache. Only known
    top-level keys are accepted, so a typo can't inject junk into the config."""
    allowed = set(defaults())
    clean = {k: v for k, v in (patch or {}).items() if k in allowed}
    row = await session.get(Pricing, KEY)
    stored = _merge(dict(row.value or {}) if row else {}, clean)
    if row is None:
        session.add(Pricing(key=KEY, value=stored))
    else:
        row.value = stored
    await session.commit()
    try:
        await redis_client.delete(_CACHE_KEY)
        # FIX: PERF-A1 - the Mini App sections cache (api.routers.miniapp) is derived
        # from the ``miniapp_sections`` override, so an admin toggling a section must
        # invalidate it too — otherwise the storefront lags by up to its TTL.
        if "miniapp_sections" in clean:
            await redis_client.delete("cache:miniapp_sections")
    except Exception as exc:  # noqa: BLE001
        import structlog
        structlog.get_logger().warning('core.services.pricing.set_config_failed', error=str(exc))
        # FIX: AUDIT12-L1 - was silent except: pass
    return await get_config(session)


# ---- convenience getters (used by quota / payments / keyboards) -------------
def _int(v: Any, fallback: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return fallback


def _from_map(m: dict, key: int) -> Any:
    """Look up an int key in a string-keyed map (all price-map keys are stringified
    in defaults() so they match JSON-stored overrides)."""
    return m.get(str(key), m.get(key))


def _parse_dt(value: Any) -> datetime | None:
    """Parse an ISO datetime, UTC-normalised. None/blank/malformed -> None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _sale_percent(cfg: dict) -> int:
    """Active global-sale discount percent for ``cfg`` (0 when off / not-yet-started /
    expired). Capped at 95 so a discounted price can never fall to zero."""
    sale = cfg.get("sale") or {}
    pct = _int(sale.get("percent"), 0)
    if pct <= 0:
        return 0
    now = datetime.now(UTC)
    # End bound: a present-but-malformed "until" is treated as expired (fail safe —
    # never run an unbounded sale off a typo).
    raw_until = sale.get("until")
    if raw_until:
        end = _parse_dt(raw_until)
        if end is None or now >= end:
            return 0
    # Start bound: a scheduled sale stays off until "from" is reached. A malformed
    # "from" is ignored (so it can't accidentally suppress a live sale).
    start = _parse_dt(sale.get("from"))
    if start is not None and now < start:
        return 0
    return min(95, pct)


def _discounted(stars: int, pct: int) -> int:
    """Apply a sale percent to a Stars price (min 1)."""
    if pct <= 0 or stars <= 0:
        return stars
    return max(1, round(stars * (100 - pct) / 100))


def discount(stars: int, pct: int) -> int:
    """Public: apply a sale percent to a Stars price (min 1, no-op when pct<=0). Used
    by keyboards to render the pre-sale price next to the discounted one with the
    SAME rounding the charge path uses, so display and charge always agree."""
    return _discounted(stars, pct)


async def limits(session: AsyncSession) -> dict[str, int]:
    base = defaults()["limits"]
    over = (await get_config(session)).get("limits", {})
    return {k: _int(over.get(k, base[k]), base[k]) for k in base}


async def subscription_price(
    session: AsyncSession, product: str, months: int, *, apply_sale: bool = True
) -> int | None:
    """Charged Stars for a subscription. ``apply_sale=False`` returns the base price so
    checkout can apply max(sale, user-discount) once instead of the sale alone."""
    cfg = await get_config(session)
    val = _from_map(cfg.get("subscription_prices", {}).get(product) or {}, months)
    pct = _sale_percent(cfg) if apply_sale else 0
    return _discounted(_int(val, 0), pct) if val is not None else None


async def pack_price(
    session: AsyncSession, pack: str, qty: int, *, apply_sale: bool = True
) -> int | None:
    cfg = await get_config(session)
    val = _from_map(cfg.get("pack_prices", {}).get(pack) or {}, qty)
    pct = _sale_percent(cfg) if apply_sale else 0
    return _discounted(_int(val, 0), pct) if val is not None else None


async def credit_pack_price(
    session: AsyncSession, qty: int, *, apply_sale: bool = True
) -> int | None:
    cfg = await get_config(session)
    val = _from_map(cfg.get("credit_packs", {}), qty)
    pct = _sale_percent(cfg) if apply_sale else 0
    return _discounted(_int(val, 0), pct) if val is not None else None


async def subscription_prices(
    session: AsyncSession, product: str, *, apply_sale: bool = True
) -> dict[int, int]:
    """Full {months: stars} map for a product (int keys), for keyboards. Pass
    ``apply_sale=False`` to get the pre-sale prices (keyboards show both)."""
    cfg = await get_config(session)
    pct = _sale_percent(cfg) if apply_sale else 0
    m = cfg.get("subscription_prices", {}).get(product) or {}
    return {int(k): _discounted(_int(v, 0), pct) for k, v in m.items()}


async def pack_prices_for(
    session: AsyncSession, pack: str, *, apply_sale: bool = True
) -> dict[int, int]:
    """Full {qty: stars} map for a pack (int keys), for keyboards. ``apply_sale=False``
    returns pre-sale prices."""
    cfg = await get_config(session)
    pct = _sale_percent(cfg) if apply_sale else 0
    m = cfg.get("pack_prices", {}).get(pack) or {}
    return {int(k): _discounted(_int(v, 0), pct) for k, v in m.items()}


async def credit_packs(
    session: AsyncSession, *, apply_sale: bool = True
) -> dict[int, int]:
    """Full {qty: stars} credit-top-up map (int keys). ``apply_sale=False`` returns
    pre-sale prices."""
    cfg = await get_config(session)
    pct = _sale_percent(cfg) if apply_sale else 0
    m = cfg.get("credit_packs", {})
    return {int(k): _discounted(_int(v, 0), pct) for k, v in m.items()}


async def avatar_price(session: AsyncSession, *, apply_sale: bool = True) -> int:
    cfg = await get_config(session)
    pct = _sale_percent(cfg) if apply_sale else 0
    return _discounted(_int(cfg.get("avatar_price"), AVATAR_PRICE), pct)


async def sponsored_free_daily(session: AsyncSession) -> int:
    """How many FREE sponsored-effect generations a user gets per UTC day (admin-set;
    0 = none). Not sale-discounted — it's a count, not a price."""
    cfg = await get_config(session)
    return max(0, _int(cfg.get("sponsored_free_daily"), 3))


async def sale_percent(session: AsyncSession) -> int:
    """Active global-sale percent right now (0 = no active sale). Lets keyboards show
    the pre-sale price struck through next to the discounted one."""
    return _sale_percent(await get_config(session))


async def sale_state(session: AsyncSession) -> dict[str, Any]:
    """Current sale config + status for admin/display. ``active`` = discounting now;
    ``scheduled`` = configured with a future start that hasn't begun yet."""
    cfg = await get_config(session)
    sale = cfg.get("sale") or {}
    pct = _int(sale.get("percent"), 0)
    now = datetime.now(UTC)
    start = _parse_dt(sale.get("from"))
    end = _parse_dt(sale.get("until"))
    expired = bool(sale.get("until")) and (end is None or now >= end)
    scheduled = pct > 0 and start is not None and now < start and not expired
    return {
        "percent": pct,
        "from": sale.get("from"),
        "until": sale.get("until"),
        "active": _sale_percent(cfg) > 0,
        "scheduled": scheduled,
    }


async def promos(session: AsyncSession) -> dict[str, int]:
    """Promo-mechanics knobs (welcome / first-purchase bonus + cashback %), int-
    coerced. Defaults are all 0 (off) so promos stay inert until an admin enables them."""
    base = defaults()["promos"]
    over = (await get_config(session)).get("promos", {})
    return {k: _int(over.get(k, base[k]), base[k]) for k in base}


async def doc_links(session: AsyncSession) -> dict[str, str]:
    """Admin-set "Инструкция" URLs for photo/video service configs, keyed by
    service doc_link_key. Only http(s) values are returned, so a malformed entry
    can never render an unsafe button. Empty by default (no third-party links)."""
    raw = (await get_config(session)).get("doc_links") or {}
    out: dict[str, str] = {}
    if isinstance(raw, dict):
        for key, url in raw.items():
            u = str(url or "").strip()
            if u.startswith(("https://", "http://")):
                out[str(key)] = u
    return out


_OPT_STR_FIELDS = ("qualities", "ratios", "resolutions")
_OPT_INT_FIELDS = ("counts", "durations")
# Structural toggle buttons an admin may hide per service (config keyboards gate on
# these). Hiding only removes an option, so it is always cost-safe.
_HIDEABLE_TOGGLES = {"audio", "fourk", "seed", "enhance", "modes"}


def _sanitize_service_override(ov: dict) -> dict:
    """Keep only well-formed option lists from one service's admin override."""
    clean: dict[str, list] = {}
    for f in _OPT_STR_FIELDS:
        if isinstance(ov.get(f), list):
            vals = [str(x).strip() for x in ov[f] if str(x).strip()]
            if vals:
                clean[f] = vals
    for f in _OPT_INT_FIELDS:
        if isinstance(ov.get(f), list):
            vals: list[int] = []
            for x in ov[f]:
                try:
                    vals.append(int(x))
                except (TypeError, ValueError):
                    continue
            if vals:
                clean[f] = vals
    if isinstance(ov.get("models"), list):
        pairs = []
        for x in ov["models"]:
            if isinstance(x, (list, tuple)) and len(x) == 2 and str(x[0]).strip():
                pairs.append([str(x[0]).strip(), str(x[1]).strip() or str(x[0]).strip()])
        if pairs:
            clean["models"] = pairs
    # Structural toggles the admin chose to HIDE for this service (show/hide only —
    # hiding just removes an option, so it can never cause an undercharge).
    if isinstance(ov.get("hide"), list):
        hide = [str(x) for x in ov["hide"] if str(x) in _HIDEABLE_TOGGLES]
        if hide:
            clean["hide"] = hide
    return clean


async def service_options(session: AsyncSession) -> dict[str, dict]:
    """Admin overrides for per-service generation option buttons, sanitized. Maps
    service key -> {field: [values]} for the fields the admin chose to override;
    everything else falls back to the code spec. Only the button lists are affected."""
    raw = (await get_config(session)).get("service_options") or {}
    out: dict[str, dict] = {}
    if isinstance(raw, dict):
        for key, ov in raw.items():
            if isinstance(ov, dict):
                clean = _sanitize_service_override(ov)
                if clean:
                    out[str(key)] = clean
    return out


async def preset_roles(session: AsyncSession) -> list[dict[str, str]]:
    """Curated personas for /roles (ТЗ §3), admin-editable. Each item is
    {key, title, prompt}; malformed entries are dropped."""
    raw = (await get_config(session)).get("preset_roles") or []
    out = []
    for r in raw:
        if isinstance(r, dict) and r.get("key") and r.get("prompt"):
            out.append({
                "key": str(r["key"]),
                "title": str(r.get("title") or r["key"]),
                "prompt": str(r["prompt"]),
                "desc": str(r.get("desc") or ""),   # 1-line preview shown in /roles
            })
    return out


async def preset_role(session: AsyncSession, key: str) -> dict[str, str] | None:
    """Resolve a single preset role by key (None when unknown)."""
    for r in await preset_roles(session):
        if r["key"] == key:
            return r
    return None


async def custom_buttons(session: AsyncSession) -> list[dict]:
    """Admin-defined inline link buttons (ТЗ §8). Each has at least {text, url}
    (malformed dropped). Optional layout fields are passed through for the keyboard
    builder: ``enabled`` (only when explicitly False), ``row`` (int — buttons that
    share a row index render on one keyboard row) and ``icon`` (emoji prefix)."""
    raw = (await get_config(session)).get("custom_buttons") or []
    out: list[dict] = []
    for b in raw:
        if not (isinstance(b, dict) and b.get("text") and b.get("url")):
            continue
        item: dict = {"text": str(b["text"]), "url": str(b["url"])}
        if b.get("id"):
            item["id"] = str(b["id"])  # stable id → /r/{id} click tracking
        if b.get("enabled") is False:
            item["enabled"] = False
        if isinstance(b.get("row"), int) and not isinstance(b.get("row"), bool):
            item["row"] = b["row"]
        if b.get("icon"):
            item["icon"] = str(b["icon"])
        out.append(item)
    return out


async def retention(session: AsyncSession) -> dict[str, int]:
    """Result-retention days (ТЗ §5): {job_days, gallery_days}. 0 = keep forever."""
    r = (await get_config(session)).get("retention") or {}
    base = defaults()["retention"]
    return {k: max(0, _int(r.get(k, base[k]), base[k])) for k in base}


async def ads(session: AsyncSession) -> dict[str, Any]:
    """Ad settings for free users (ТЗ §6): {enabled, every_n, text}."""
    a = (await get_config(session)).get("ads") or {}
    fallback = defaults()["ads"]
    return {
        "enabled": bool(a.get("enabled", False)),
        "every_n": max(1, _int(a.get("every_n"), fallback["every_n"])),
        "text": str(a.get("text") or fallback["text"]),
    }


async def branding(session: AsyncSession) -> dict[str, str]:
    """Branding/welcome-media config (ТЗ §1/§3): {start_media_url, start_media_type}."""
    b = (await get_config(session)).get("branding") or {}
    mtype = str(b.get("start_media_type") or "photo")
    return {
        "start_media_url": str(b.get("start_media_url") or ""),
        "start_media_type": mtype if mtype in ("photo", "video") else "photo",
    }


async def chat_config(session: AsyncSession) -> dict[str, Any]:
    """Chat behaviour knobs (ТЗ §3): {memory_pairs, markdown_enabled}. memory_pairs
    is clamped to a sane 1..20 range."""
    c = (await get_config(session)).get("chat") or {}
    fallback = defaults()["chat"]
    pairs = _int(c.get("memory_pairs"), fallback["memory_pairs"])
    return {
        "memory_pairs": max(1, min(20, pairs)),
        "markdown_enabled": bool(c.get("markdown_enabled", fallback["markdown_enabled"])),
        "groups_enabled": bool(c.get("groups_enabled", fallback["groups_enabled"])),
        "streaming_enabled": bool(c.get("streaming_enabled", fallback["streaming_enabled"])),
    }


async def generation(session: AsyncSession) -> dict[str, int]:
    """Generation knobs (ТЗ §5): {image_variants} clamped to 1..4."""
    g = (await get_config(session)).get("generation") or {}
    return {"image_variants": max(1, min(4, _int(g.get("image_variants"), 1)))}


async def referral_fraud(session: AsyncSession) -> dict[str, Any]:
    """Referral anti-fraud config (ТЗ §6): {enabled, min_referred_age_hours}."""
    f = (await get_config(session)).get("referral_fraud") or {}
    base = defaults()["referral_fraud"]
    return {
        "enabled": bool(f.get("enabled", base["enabled"])),
        "min_referred_age_hours": max(0, _int(
            f.get("min_referred_age_hours"), base["min_referred_age_hours"])),
    }


async def maintenance(session: AsyncSession) -> dict[str, Any]:
    """Maintenance-mode state (ТЗ §8): {enabled, message}."""
    m = (await get_config(session)).get("maintenance") or {}
    fallback = defaults()["maintenance"]
    return {
        "enabled": bool(m.get("enabled", False)),
        "message": str(m.get("message") or fallback["message"]),
    }


async def section_state(session: AsyncSession, name: str) -> dict[str, Any]:
    """A menu section's {enabled, soon} — the admin override merged over the default.
    Unknown sections are treated as enabled (so a new section can't accidentally be
    hidden before it has a config entry)."""
    base = defaults()["sections"].get(name, {"enabled": True, "soon": ""})
    override = ((await get_config(session)).get("sections") or {}).get(name) or {}
    return {
        "enabled": bool(override.get("enabled", base["enabled"])),
        "soon": str(override.get("soon") or base["soon"]),
    }


# A generation pack is only sold when its menu section is ON — otherwise users
# would buy credits for a feature that still shows "coming soon".
PACK_SECTION = {"image_pack": "images", "video_pack": "video", "music_pack": "music"}


async def pack_section_state(session: AsyncSession, pack: str) -> dict[str, Any]:
    """The {enabled, soon} of the section a pack belongs to. Unknown pack → enabled
    (a pack not tied to a media section is never section-gated)."""
    section = PACK_SECTION.get(pack)
    if section is None:
        return {"enabled": True, "soon": ""}
    return await section_state(session, section)


async def queue_priority_enabled(session: AsyncSession) -> bool:
    """Whether Premium users' generation jobs jump the queue (ТЗ §8). On by default."""
    q = (await get_config(session)).get("queue") or {}
    return bool(q.get("premium_priority_enabled", True))


async def document_cost(session: AsyncSession) -> int:
    """Generations charged per document Q&A request (ТЗ §5), admin-editable."""
    d = (await get_config(session)).get("documents") or {}
    return max(1, _int(d.get("cost"), defaults()["documents"]["cost"]))


async def search_system_prompt(session: AsyncSession) -> str:
    """System prompt for internet search (ТЗ §3), admin-editable. Falls back to the
    default when unset/blank."""
    fallback = defaults()["search"]["system_prompt"]
    s = (await get_config(session)).get("search") or {}
    return str(s.get("system_prompt") or fallback)


async def notifications(session: AsyncSession) -> dict[str, Any]:
    """Auto-notification settings (ТЗ §7), with bools/ints coerced from the live
    config over the defaults."""
    base = defaults()["notifications"]
    over = (await get_config(session)).get("notifications", {})
    out: dict[str, Any] = {}
    for k, default in base.items():
        v = over.get(k, default)
        out[k] = bool(v) if isinstance(default, bool) else _int(v, default)
    return out


async def vip_config(session: AsyncSession) -> dict[str, Any]:
    """VIP/loyalty config: {enabled, tiers[]} with tiers sorted ascending by
    min_spent and int-coerced. Empty/disabled config returns enabled=False."""
    cfg = (await get_config(session)).get("vip") or {}
    tiers = []
    for t in cfg.get("tiers") or []:
        if not isinstance(t, dict):
            continue
        tiers.append({
            "name": str(t.get("name", "")),
            "min_spent": _int(t.get("min_spent"), 0),
            "bonus_daily": _int(t.get("bonus_daily"), 0),
            "bonus_weekly": _int(t.get("bonus_weekly"), 0),
        })
    tiers.sort(key=lambda t: t["min_spent"])
    return {"enabled": bool(cfg.get("enabled", False)), "tiers": tiers}
