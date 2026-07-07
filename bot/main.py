"""aiogram entrypoint. Long-polling in dev, webhook in prod (BOT_MODE)."""
from __future__ import annotations

import asyncio
from contextlib import suppress  # FIX: B1 - needed for L2 finally block

import structlog
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import (
    DefaultKeyBuilder,  # FIX: AUDIT12-17 - base for our custom key builder
    KeyBuilder,  # FIX: AUDIT12-17 - protocol we implement
    RedisStorage,
)
from aiogram.fsm.state import State
from aiogram.types import BotCommand, ErrorEvent, TelegramObject

from bot.handlers import setup_routers
from bot.middlewares import (
    BanMiddleware,
    ChannelGateMiddleware,
    DBSessionMiddleware,
    MaintenanceMiddleware,
    ThrottlingMiddleware,
    UserContextMiddleware,
)
from core.config import settings
from core.logging_setup import setup_logging
from core.redis_client import redis_client

# Console + rotating file logging (logs/app.log) — same sink the Maintenance Log
# Center tails. Replaces a bare basicConfig so bot logs also reach the file.
setup_logging()
log = structlog.get_logger()

if settings.sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env, traces_sample_rate=0.1)

# Command order shown in the Telegram menu bar (owner-specified).
COMMAND_ORDER = [
    "start", "account", "premium", "deletecontext", "photo", "video",
    "music", "s", "model", "settings", "help", "privacy",
]

# Localized menu-bar descriptions (falls back to EN, then RU).
COMMAND_DESC = {
    "ru": {
        "start": "Описание бота", "account": "Профиль и баланс",
        "premium": "Тарифы и Premium", "deletecontext": "Очистить контекст",
        "photo": "Создание изображений", "video": "Создание видео",
        "music": "Создание музыки", "s": "Поиск в Интернете",
        "model": "Выбор модели", "settings": "Настройки бота",
        "help": "Помощь", "privacy": "Документы",
    },
    "en": {
        "start": "About the bot", "account": "Profile & balance",
        "premium": "Plans & Premium", "deletecontext": "Clear context",
        "photo": "Create images", "video": "Create video",
        "music": "Create music", "s": "Internet search",
        "model": "Choose model", "settings": "Settings",
        "help": "Help", "privacy": "Documents",
    },
    "es": {
        "start": "Sobre el bot", "account": "Perfil y saldo", "premium": "Planes y Premium",
        "deletecontext": "Borrar contexto", "photo": "Crear imágenes", "video": "Crear vídeo",
        "music": "Crear música", "s": "Búsqueda web", "model": "Elegir modelo",
        "settings": "Ajustes", "help": "Ayuda", "privacy": "Documentos",
    },
    "fr": {
        "start": "À propos du bot", "account": "Profil et solde", "premium": "Offres et Premium",
        "deletecontext": "Effacer le contexte", "photo": "Créer des images", "video": "Créer une vidéo",
        "music": "Créer de la musique", "s": "Recherche web", "model": "Choisir le modèle",
        "settings": "Paramètres", "help": "Aide", "privacy": "Documents",
    },
    "pt": {
        "start": "Sobre o bot", "account": "Perfil e saldo", "premium": "Planos e Premium",
        "deletecontext": "Limpar contexto", "photo": "Criar imagens", "video": "Criar vídeo",
        "music": "Criar música", "s": "Busca na web", "model": "Escolher modelo",
        "settings": "Configurações", "help": "Ajuda", "privacy": "Documentos",
    },
    "uz": {
        "start": "Bot haqida", "account": "Profil va balans", "premium": "Tariflar va Premium",
        "deletecontext": "Kontekstni tozalash", "photo": "Rasm yaratish", "video": "Video yaratish",
        "music": "Musiqa yaratish", "s": "Internet qidiruv", "model": "Modelni tanlash",
        "settings": "Sozlamalar", "help": "Yordam", "privacy": "Hujjatlar",
    },
    "ar": {
        "start": "حول البوت", "account": "الملف والرصيد", "premium": "الباقات و Premium",
        "deletecontext": "مسح السياق", "photo": "إنشاء صور", "video": "إنشاء فيديو",
        "music": "إنشاء موسيقى", "s": "بحث إنترنت", "model": "اختيار النموذج",
        "settings": "الإعدادات", "help": "مساعدة", "privacy": "المستندات",
    },
    "zh": {
        "start": "关于机器人", "account": "资料与余额", "premium": "套餐与会员",
        "deletecontext": "清除上下文", "photo": "创建图片", "video": "创建视频",
        "music": "创建音乐", "s": "联网搜索", "model": "选择模型",
        "settings": "设置", "help": "帮助", "privacy": "文档",
    },
}


def commands_for(locale: str) -> list[BotCommand]:
    desc = COMMAND_DESC.get(locale) or COMMAND_DESC["en"]
    ru = COMMAND_DESC["ru"]
    return [
        BotCommand(command=c, description=desc.get(c) or ru.get(c, "")) for c in COMMAND_ORDER  # FIX: AUDIT-118
    ]


COMMANDS = commands_for("ru")


_dp: Dispatcher | None = None


async def on_bot_error(event: ErrorEvent) -> bool:
    """Global safety net for any unhandled handler exception (a parse error on a
    malformed/forged callback, a DB/provider hiccup a handler didn't catch, …).

    Without this, aiogram logs the error but the user is left with NO feedback — and
    a callback_query button SPINS for ~30s until Telegram times it out. Here we log
    the failure with context and, for a callback, answer it so the button settles
    with a friendly notice. Returns True so aiogram treats the error as handled."""
    update = event.update
    cq = getattr(update, "callback_query", None)
    log.error(
        "bot.unhandled_error",
        exc_info=event.exception,
        update_id=getattr(update, "update_id", None),
        callback_data=getattr(cq, "data", None),
    )
    if cq is not None:
        try:
            # FIX: B4 - use a language-neutral emoji string (was: _t("common.error_generic")
            # which doesn't exist in any locale → returned raw key string to the user).
            await cq.answer("⚠️", show_alert=True)
        except Exception:  # noqa: BLE001 — the callback may already be expired/answered
            pass
    return True


class MultiBotKeyBuilder(DefaultKeyBuilder):
    """FIX: AUDIT12-17 - include bot_id in FSM Redis keys to prevent state bleed
    across bot instances in multi-bot setups. Key format: ``fsm:{bot_id}:{chat_id}:{user_id}``.
    """
    def build(self, key: TelegramObject, state: State | None = None) -> str:  # type: ignore[override]
        bot_id = 0
        bot = getattr(key, "bot", None)
        if bot is not None:
            try:
                token = getattr(bot, "token", "")
                if token:
                    parts = str(token).split(":")
                    if parts and parts[0].isdigit():
                        bot_id = int(parts[0])
            except Exception:  # noqa: BLE001
                bot_id = 0
        chat_id = getattr(key, "chat_id", 0) or 0
        user_id_obj = getattr(key, "from_user", None)
        user_id = (getattr(user_id_obj, "id", 0) if user_id_obj else 0) or 0
        return f"fsm:{bot_id}:{chat_id}:{user_id}"


def build_dispatcher() -> Dispatcher:
    # Handler routers are module-level singletons, so the dispatcher is built once
    # per process and cached (repeat calls return the same instance).
    global _dp
    if _dp is not None:
        return _dp
    # FIX: L1 - expire abandoned FSM states after 24h (was: never expire → unbounded Redis growth).
    # FIX: AUDIT12-17 - use MultiBotKeyBuilder so multi-bot setups don't bleed FSM state.
    dp = Dispatcher(storage=RedisStorage(
        redis=redis_client, state_ttl=86400, data_ttl=86400,
        key_builder=MultiBotKeyBuilder(),
    ))
    # Outer middleware order (each wraps the next):
    #  1. Throttling FIRST — a flooding user is dropped on a Redis-only check
    #     before any DB session/query is opened, so spam costs no Postgres round-trip.
    #  2. DB session must wrap user-loading.
    #  3. User/locale context.
    dp.update.outer_middleware(ThrottlingMiddleware())
    dp.update.outer_middleware(DBSessionMiddleware())
    dp.update.outer_middleware(UserContextMiddleware())
    # Ban enforcement + Gate #1 (channel subscription) on message/callback, where
    # the user/session are already populated by the outer middlewares. Ban runs
    # before the gate/handlers so a banned user is blocked everywhere (not only in
    # handlers that check is_banned themselves).
    dp.message.middleware(BanMiddleware())
    dp.callback_query.middleware(BanMiddleware())
    # FIX: H1 - register BanMiddleware on pre_checkout_query too, so a banned user
    # cannot complete a Stars payment (pre_checkout would otherwise approve ok=True,
    # the user gets charged, then successful_payment is blocked by BanMiddleware —
    # charged but receives nothing).
    dp.pre_checkout_query.middleware(BanMiddleware())
    # Maintenance mode: after ban (banned users handled first), before the gate/
    # handlers — blocks non-admins while maintenance is enabled in live config.
    dp.message.middleware(MaintenanceMiddleware())
    dp.callback_query.middleware(MaintenanceMiddleware())
    dp.pre_checkout_query.middleware(MaintenanceMiddleware())  # FIX: H1
    dp.message.middleware(ChannelGateMiddleware())
    dp.callback_query.middleware(ChannelGateMiddleware())
    dp.pre_checkout_query.middleware(ChannelGateMiddleware())  # FIX: H1
    # FIX: AUDIT-12 - register Ban/Maintenance/Gate on inline_query too
    dp.inline_query.middleware(BanMiddleware())
    dp.inline_query.middleware(MaintenanceMiddleware())
    dp.inline_query.middleware(ChannelGateMiddleware())
    dp.include_router(setup_routers())
    # Global error recovery: every handler exception lands here (see on_bot_error),
    # so a crash never leaves a spinning callback button or a silent failure.
    dp.errors.register(on_bot_error)
    _dp = dp
    return dp


def build_bot() -> Bot:
    # One shared Bot per process (see core.bot_client): the dispatcher and the
    # API-side notifiers (webhook payment notices, Mini App invoices, admin Stars
    # refunds) reuse a single aiohttp session instead of opening one per call.
    from core.bot_client import get_bot

    return get_bot()


async def _setup_menu_button(bot: Bot) -> None:
    """Bottom-left button = ≡ commands menu. The Mini App launcher comes from the
    Main Mini App configured in BotFather (profile "Открыть приложение" + chat
    header button), so the user gets BOTH the commands menu AND the Mini App."""
    from aiogram.types import MenuButtonCommands

    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    log.info("bot.menu_button", kind="commands")


async def _prepare_bot(bot: Bot) -> None:
    """Per-bot startup: commands, menu button, drop any stale webhook."""
    await bot.set_my_commands(COMMANDS)
    await _setup_menu_button(bot)
    await bot.delete_webhook(drop_pending_updates=True)


async def _multi_bots() -> list[Bot]:
    """Build a Bot per ACTIVE BotInstance (ТЗ §0 multi-bot), recording each one's
    Telegram identity + the tg_bot_id → instance_id tenant map. Returns [] when no
    instances are configured (single-bot deployments fall back to the env token)."""
    from aiogram.client.default import DefaultBotProperties

    from core.db import SessionFactory
    from core.services import bots as bots_svc

    async with SessionFactory() as session:
        specs = await bots_svc.active_launch_specs(session)
        if not specs:
            return []
        built: list[Bot] = []
        for spec in specs:
            b = Bot(spec.token, default=DefaultBotProperties(parse_mode=None))
            try:
                me = await b.get_me()
            except Exception:  # noqa: BLE001 — a bad token must not sink the others
                log.warning("multibot.bad_token", instance_id=spec.instance_id)
                await b.session.close()
                continue
            bots_svc.register_bot(me.id, spec.instance_id)
            # FIX: F9 - wrap record_identity in try/except so a DB hiccup can't sink the
            # whole multi-bot fleet (contradicting the "bad token must not sink others"
            # comment above). On failure: log + close the leaked Bot session + continue.
            try:
                await bots_svc.record_identity(
                    session, spec.instance_id, tg_bot_id=me.id, username=me.username
                )
            except Exception:  # noqa: BLE001 — DB hiccup must not sink this bot
                # FIX: H2 - rollback the session so a PendingRollbackError doesn't
                # cascade to every subsequent bot in the loop (sinking the fleet).
                log.warning("multibot.record_identity_failed", instance_id=spec.instance_id)
                await session.rollback()
                await b.session.close()
                continue
            built.append(b)
        return built


async def run_polling() -> None:
    from core.lifecycle import cancel_and_drain
    from core.services import gateway_keys, i18n_overrides, provider_keys

    dp = build_dispatcher()
    # Apply admin-managed provider API keys + payment-gateway credentials +
    # localization overrides, kept fresh so admin changes reach this process without a
    # restart. Hold the loop handles so they can be cancelled on shutdown — a bare
    # create_task would outlive the dispatcher, leaking a background task parked on a
    # DB session.
    await provider_keys.load_once()
    await gateway_keys.load_once()
    await i18n_overrides.load_once()
    refreshers = [
        asyncio.create_task(provider_keys.refresh_loop()),
        asyncio.create_task(gateway_keys.refresh_loop()),
        asyncio.create_task(i18n_overrides.refresh_loop()),
    ]
    # FIX: F10 - the try/finally must cover _multi_bots() and _prepare_bot() too, not
    # just start_polling(). Otherwise a failure in either orphans the 3 refresher tasks
    # (cancel_and_drain never runs) with half-open DB sessions — the exact leak the
    # comment below claims to prevent.
    bots: list = []  # FIX: B2 - initialize before try so finally doesn't UnboundLocalError
    try:
        # Multi-bot (ТЗ §0): poll every active white-label BotInstance through this one
        # dispatcher. With no instances configured, fall back to the single env-token bot.
        bots = await _multi_bots()
        if not bots:
            bots = [build_bot()]
        for bot in bots:
            await _prepare_bot(bot)
        log.info("bot.start", mode="polling", bots=len(bots))
        await dp.start_polling(*bots)
    finally:
        # Stop the refreshers when polling ends (SIGTERM) so neither outlives the
        # process with a half-open DB session — mirrors the API/worker lifespans.
        await cancel_and_drain(*refreshers)
        # FIX: L2 - close Bot aiohttp sessions if setup failed before start_polling.
        for _bot in bots:
            with suppress(Exception):
                await _bot.session.close()


async def run_webhook() -> None:
    """Webhook mode is served by the FastAPI app (api/main.py) which feeds
    updates into this dispatcher. Here we only register the webhook URL, then
    stay alive: this process has nothing left to do, but exiting under a
    `restart: always` policy would loop the container and re-call set_webhook /
    set_my_commands on every restart. Blocking keeps it a healthy long-running
    service that registers the webhook exactly once per start."""
    bot = build_bot()
    try:
        await bot.set_my_commands(COMMANDS)
        await _setup_menu_button(bot)
        await bot.set_webhook(
            settings.webhook_url,
            drop_pending_updates=True,
            secret_token=settings.effective_webhook_secret,
        )
        log.info("bot.webhook_set", url=settings.webhook_url)
        # Park forever (until SIGTERM); the api service handles updates.
        await asyncio.Event().wait()
    finally:
        await bot.session.close()


def main() -> None:
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN is not set — copy .env.example to .env first.")
    if settings.bot_mode == "webhook":
        asyncio.run(run_webhook())
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
