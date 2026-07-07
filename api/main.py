"""FastAPI app: serves the Mini App REST API, the Telegram webhook (when
BOT_MODE=webhook) and payment-gateway webhooks. Shares the Core Backend + DB
with the bot."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.admin.router import admin_router
from api.routers import gallery, health, miniapp, redirect, webhooks
from core.config import settings
from core.logging_setup import setup_logging

# Console + rotating file logging (logs/app.log) so the Maintenance Log Center can
# tail real application logs in this process.
setup_logging()

if settings.sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env, traces_sample_rate=0.1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Apply admin-managed provider API keys + localization overrides before serving.
    import asyncio
    import logging

    from core.services import gateway_keys, i18n_overrides, provider_keys

    logging.getLogger("api").info(
        "Core API starting (env=%s, mode=%s)", settings.env, settings.bot_mode
    )
    await provider_keys.load_once()
    await gateway_keys.load_once()
    await i18n_overrides.load_once()
    # Keep BOTH snapshots fresh in EVERY worker process. Prod runs gunicorn -w 4, so a
    # single API worker has its own in-memory settings/override snapshot; an admin
    # write (set_keys / set_override) mutates only the ONE worker that served it.
    # Without a refresh loop the other workers keep stale keys/translations until a
    # restart — a newly-entered AI key would then work for only ~1/N of requests, and
    # the webhook bot (served by this same pool) would fail intermittently. The
    # polling bot starts the same loops; this is the webhook/multi-worker analogue.
    refresh_tasks = [
        asyncio.create_task(provider_keys.refresh_loop()),
        asyncio.create_task(gateway_keys.refresh_loop()),
        asyncio.create_task(i18n_overrides.refresh_loop()),
    ]
    # Bot dispatcher is attached lazily only in webhook mode.
    if settings.bot_mode == "webhook":
        from bot.main import build_bot, build_dispatcher

        app.state.bot = build_bot()
        app.state.dp = build_dispatcher()
    yield
    from core.lifecycle import cancel_and_drain

    await cancel_and_drain(*refresh_tasks)
    # Close the process-wide shared Bot's aiohttp session (it may have been created
    # lazily by the Mini App invoice / payment-notify / refund paths even in
    # polling mode, where this API process still serves the Mini App).
    from core.bot_client import close_bot

    await close_bot()


app = FastAPI(title="ИИ Бот №1 — Core API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Same-origin in prod; set CORS_ORIGINS to the Mini App URL(s) to lock down.
    allow_origins=settings.cors_origin_list,
    # The admin SPA authenticates with the httpOnly `admin_access` cookie and sends
    # every request with `credentials: include`. Without this flag the browser omits
    # `Access-Control-Allow-Credentials: true` and BLOCKS reading the response on any
    # cross-origin call — so a cross-origin admin (dev vite on another port, or a
    # split api.<domain> deploy) can't even read a 401, and login silently surfaces
    # "wrong password" instead of the 2FA prompt. Prod locks cors_origin_list to the
    # exact origin(s) (config rejects "*" in public deploy), so reflecting credentials
    # is safe; Starlette echoes the specific Origin, never a wildcard, alongside it.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(miniapp.router, prefix="/api")
app.include_router(gallery.router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(webhooks.router)
# /r/{id} click-tracking redirect for /links buttons — registered before the greedy
# SPA mount at "/" so it isn't swallowed by the static file handler.
app.include_router(redirect.router)

# Admin-uploaded effect previews (mounted before the greedy SPA mount at "/").
_MEDIA = os.path.join(os.path.dirname(__file__), "..", "media")
os.makedirs(_MEDIA, exist_ok=True)
app.mount("/media", StaticFiles(directory=_MEDIA), name="media")

# Serve the built admin SPA under /admin (same origin as /api/admin so its
# relative API calls resolve). Built with base "/admin/".
# A bare "/admin" (no trailing slash) would 404 against the mount, so redirect it
# to "/admin/" — users routinely type the URL without the slash.
@app.get("/admin", include_in_schema=False)
def _admin_slash_redirect() -> RedirectResponse:
    return RedirectResponse(url="/admin/")


_ADMIN_DIST = os.path.join(os.path.dirname(__file__), "..", "admin", "dist")
if os.path.isdir(_ADMIN_DIST):
    app.mount("/admin", StaticFiles(directory=_ADMIN_DIST, html=True), name="admin")

# Serve the built Mini App SPA from the same origin as the API, so a single
# public HTTPS URL serves both the WebApp and its /api calls.
_DIST = os.path.join(os.path.dirname(__file__), "..", "miniapp", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="miniapp")
