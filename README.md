# ИИ Бот №1 — Multi-Model AI Telegram Bot + Mini App

Production clone of `@GPT4Telegrambot` (ChatGPT · Claude · Gemini · DeepSeek ·
Midjourney · Kling · Suno …) built per [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).

Stack: **aiogram 3 · FastAPI · SQLAlchemy 2 (async) · PostgreSQL · Redis · ARQ ·
MinIO · React (Mini App + Admin)**, one Core Backend shared by bot and Mini App.

## 📚 Documentation
| Doc | What |
|-----|------|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | components, data flow, design decisions |
| [DEPLOYMENT](docs/DEPLOYMENT.md) | prod/staging deploy, upgrades, rollback, scaling |
| [ENV](docs/ENV.md) | every environment variable |
| [SECURITY](docs/SECURITY.md) | controls, hardening checklist, reporting |
| [API](docs/API.md) | endpoint surface + auth (`/docs` for live OpenAPI) |
| [MONITORING](docs/MONITORING.md) | Prometheus/Grafana/Loki/alerts |
| [BACKUP](docs/BACKUP.md) · [RESTORE](docs/RESTORE.md) | backups + restore drills |
| [CICD](docs/CICD.md) | pipelines, releases, Dependabot |
| [RUNBOOK](docs/RUNBOOK.md) · [TROUBLESHOOTING](docs/TROUBLESHOOTING.md) | on-call ops |
| [CONTRIBUTING](CONTRIBUTING.md) · [CHANGELOG](CHANGELOG.md) | dev workflow + history |

Keyless local run: `uvicorn scripts.mock_ai_server:app --port 8088` then point
`OPENAI_BASE_URL` at it. Load tests: [`loadtests/`](loadtests/README.md).

---

## Status

| Phase | Scope | State |
| --- | --- | --- |
| **0 — Scaffold** | monorepo, docker-compose, config, DB models, Alembic, i18n, AI-router abstraction, CI-ready test harness | ✅ done |
| **1 — Text core** | `/start /help /account /settings /model /deletecontext /privacy /s`, persistent keyboard, plain-text AI chat, rolling context, dual quota + gates, premium gate on models | ✅ working |
| **1 — Premium/pay** | `/premium` 3-step FSM, **Telegram Stars** invoice + activation (idempotent) | ✅ Stars; external gateways stubbed |
| **2 — Search/voice/docs** | `/s` search, **TTS 12 voices** (selector + preview + 🔊 reply), **document reading** (pdf/docx/xlsx/pptx/csv/txt, Premium, 3 gen), all 8 locales for key screens | ✅ working |
| **3 — Images** | **atomic image-pack ledger** (FOR UPDATE + refund), **pack purchase** (Stars), per-service sub-menus (GPT Image 2 / Nano Banana / Seedream / Midjourney / FLUX 2 — model/quality/ratio/seed), weekly-vs-pack budget routing, **Gate#2**, Avatar async (`/ava`), hidden `/wow` `/Midjourney` | ✅ flow done; provider calls behind adapters (TODO model ids on key arrival) |
| **4 — Video** | **video-pack** flow, 6 config services (Seedance/Veo/Grok/Kling AI/Hailuo/Pika — model/duration/res/ratio/audio/seed), **async job queue** (submit→poll→deliver→refund), **Kling Effects** (74, 7-page paginator) + **Kling Motion** (13) → photo → job | ✅ flow done; provider submit/poll behind adapters |
| **5 — Music + 4 gateways** | **music pack** + paywall, Suno/Lyria async (audio delivery), **СБП(Tribute)/ЮКасса/Stripe** providers — checkout + **signature-verified webhooks** + idempotent activation, Stars→fiat conversion | ✅ all 4 gateways wired |
| **6 — Mini App** | React 3-tab SPA (Главная/Тренды/Профиль), photo-effect generate flow (upload→quota/💎 charge→job poll→result), video-effects carousel, 5 filter categories, profile purchases via `WebApp.openInvoice` (Stars link). Backend: generation API, job polling, mini-app quota + image-credit fallback, effect catalogs. **Typechecks + builds.** | ✅ done |
| **6.5 — Admin panel** | secured `api/admin/` — **JWT + TOTP 2FA + RBAC (4 roles) + IP allow-list + audit log**; users (ban/credits/premium/reset-quota/clear-context), payments (+refund), pricing editor (superadmin), providers kill-switch, gate-channels, **broadcasts via ARQ**, dashboard. React admin SPA (login+2FA, dashboard, users, providers) — **typechecks + builds**. `scripts/create_admin.py` bootstraps the first admin. | ✅ done |
| **7 — Prod hardening** | content **moderation** (own rules + OpenAI Moderation) on all prompts, **throttling/antifraud** middleware (Redis), usage_log analytics, Sentry (bot+api), `/metrics`, DB indexes, **Caddyfile** (TLS + `admin.<domain>` IP allow-list), **docker-compose.prod.yml**, **pg_dump backups** + retention, legal templates | ✅ done |

**All phases (0–7) are implemented.** The bot, API, workers, Mini App and admin
panel run end-to-end; AI/payment provider calls sit behind adapters with
`is_available()` fallback, so they activate as real keys arrive without touching
handlers. 44 backend tests pass; both React SPAs typecheck + build.

---

## Architecture

```
Telegram ──webhook/polling──► Bot (aiogram)  ┐
Telegram ──WebApp──► Mini App (React) ─REST─► ├─► Core Backend (services + AI router)
                                              │        │
                          Admin (React) ─────►┘   PostgreSQL · Redis · ARQ workers · MinIO
```

- **PostgreSQL** — source of truth (users, subs, balances, transactions, jobs, catalogs).
- **Redis** — rolling chat context, FSM storage, rate-limits, caches.
- **AI Router** (`core/ai_router`) — one `chat()/generate()` surface over 12+
  adapters; each adapter has `is_available()` and degrades gracefully when its
  API key is missing, so the bot runs end-to-end with zero AI keys.

---

## Quick start (Docker)

```bash
cp .env.example .env          # then set BOT_TOKEN (minimum)
docker compose up -d postgres redis minio
docker compose run --rm api python -m scripts.init_db       # create tables (dev)
docker compose run --rm api python -m scripts.seed_catalogs # Kling effects/motion
docker compose up -d bot api worker
```

Bot runs in **long-polling** by default (`BOT_MODE=polling`). For production set
`BOT_MODE=webhook` + `WEBHOOK_BASE_URL`; the FastAPI app then serves
`/webhook/telegram` and feeds updates into the dispatcher.

## Quick start (local, no Docker)

```bash
uv venv --python 3.11 .venv          # a complete CPython (see note below)
uv pip install -r requirements.txt
# point DATABASE_URL/REDIS_URL at local services, then:
python -m scripts.init_db
python -m bot.main                   # bot
uvicorn api.main:app --reload        # api
arq workers.main.WorkerSettings      # job-processing workers (safe to run several)
arq workers.main.BeatSettings        # scheduler / cron — run EXACTLY ONE instance
```

> Windows note: the uv-managed standalone CPython 3.12/3.13 on this machine ship
> an **incomplete stdlib** (`enum`, `html.entities` missing). Use the python.org
> 3.11 interpreter as the venv base (`uv venv --python <path-to-python.org 3.11>`).

## Migrations

```bash
alembic revision --autogenerate -m "init"
alembic upgrade head
```

`scripts/init_db.py` is a dev shortcut (`create_all`); use Alembic in prod.

## Admin panel

```bash
python -m scripts.create_admin admin@example.com 'StrongPass!' superadmin
# scan the printed otpauth:// URI in an authenticator app, then:
cd admin && npm install && npm run build   # serve admin/dist behind admin.<domain>
```

The admin API lives under `/api/admin/*` (JWT + TOTP 2FA, RBAC, IP allow-list via
`ADMIN_IP_ALLOWLIST`).

## Production deploy

```bash
# 1. build the SPAs
(cd miniapp && npm ci && npm run build)
(cd admin   && npm ci && npm run build)
# 2. set DOMAIN + ADMIN_ALLOW_IP (and secrets) in .env, then:
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The prod overlay runs the bot in **webhook** mode behind **Caddy** (automatic
TLS), serves the Mini App at `https://$DOMAIN` and the admin panel at
`https://admin.$DOMAIN` (locked to `ADMIN_ALLOW_IP`), runs ARQ `worker`+`beat`,
and a `backup` service doing daily `pg_dump` with retention. Set `SENTRY_DSN` for
error tracking; scrape `GET /metrics` (Prometheus) for Grafana.

**Hardening built in:** content moderation on every prompt (own rules + OpenAI
Moderation), per-user Redis throttling, idempotent payments, audit log, IP
allow-list + 2FA on admin, DB indexes on hot paths, legal templates in
`docs/legal/`.

## Tests

```bash
python -m pytest -q   # 49 tests: quota/pricing/i18n/payments/admin/moderation
                      # + real-DB integration (SQLite) + bot/api wiring
```

Tests run with **zero infra** (`REDIS_URL=memory://` → fakeredis, SQLite DB) — the
same dev mode lets the bot boot without Postgres/Redis. The bot has been verified
to boot end-to-end and reach Telegram auth (only a real `BOT_TOKEN` is needed to
serve users). To confirm a live AI provider:

```bash
OPENAI_API_KEY=sk-... python -m scripts.live_check openai
```

---

## Layout

```
bot/        aiogram app — handlers, keyboards, states, middlewares
core/       shared business logic — config, db, models, services, ai_router, i18n
api/        FastAPI — Mini App REST, Telegram + payment webhooks, admin API
workers/    ARQ tasks — async generation jobs, billing cron
miniapp/    React Mini App SPA            (builds: npm i && npm run build)
admin/      React admin panel SPA         (builds: npm i && npm run build)
migrations/ Alembic
scripts/    init_db, seed_catalogs
tests/      pytest
```

## Configuration

All secrets + business numbers live in `.env` (see `.env.example`). Business
numbers (prices, quotas, multipliers, referral rewards) are additionally
overridable at runtime via the `pricing` DB table — no redeploy required.

The bot is fully navigable **without any AI/payment keys**: missing providers
return a friendly "сервис временно недоступен" and Stars is the default gateway.
