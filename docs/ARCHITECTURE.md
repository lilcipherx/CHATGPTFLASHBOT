# Architecture

## Overview
A single **Core Backend** (FastAPI + SQLAlchemy 2 async + PostgreSQL + Redis) is
shared by four surfaces:

```
                    ┌──────────────────────── Core (core/) ─────────────────────────┐
 Telegram  ──▶ bot/ │  models · services (quota/credits/packs/billing/refunds/...)   │
 WebApp    ──▶ api/ │  ai_router (text + media gateways) · payments · i18n           │
 Admin SPA ──▶ api/admin/                                                            │
 Workers   ──▶ workers/ (ARQ) ◀── Redis queue ── enqueue() from bot/api             │
                    └────────────────────────────────────────────────────────────────┘
        PostgreSQL  ·  Redis (cache + FSM + queue + rate-limit)  ·  S3/MinIO (uploads)
```

| Dir | Responsibility |
|-----|----------------|
| `bot/` | aiogram 3 routers, middlewares (throttle → DB session → user ctx → ban → channel gate), FSM, keyboards |
| `api/` | Mini App REST (`/api`), admin API (`/api/admin`), webhooks (telegram + 3 gateways), health/metrics |
| `core/` | Domain: models, services (money/quota/moderation), `ai_router`, `payments`, `i18n`, config, db, queue |
| `workers/` | ARQ jobs (video/music/photo/avatar/broadcast) + cron (subscription expiry, stuck-job sweep) |
| `miniapp/`, `admin/` | React (Vite) SPAs, served same-origin via StaticFiles/Caddy |

## Key design decisions
- **One backend, many surfaces** — bot and Mini App call the same services, so
  quota/billing/moderation rules can never diverge.
- **Atomic money** — credit/pack/quota deductions take a row-level lock
  (`SELECT … FOR UPDATE`); refunds go through one canonical `refund_job`.
- **Idempotent payments** — `transactions.gateway_tx_id` is unique; webhook
  application is safe under retries; the paid amount is validated against the
  quoted amount embedded at checkout.
- **Beat ≠ Worker** — `workers.main.WorkerSettings` (scale to N) has *no* cron;
  `BeatSettings` (exactly one replica) owns all cron jobs, so scaling never
  multiplies scheduled work.
- **Resilient AI routing** — `core/services/ai_routing.py` keeps an ordered pool
  (OmniRoute) → fallback list, with per-account cooldown (circuit breaker),
  consecutive-error auto-disable, and health tracking. Adapters carry timeouts.
- **Zero-infra dev** — `REDIS_URL=memory://` (fakeredis) + SQLite via portable
  column types; the whole suite runs with no external services.

## Request lifecycles
- **Bot message:** Update → throttle (Redis only) → DB session → load/locale user
  → ban → channel gate → router handler → service → reply.
- **Mini App generate:** signed `initData` (HMAC) → moderation → charge (atomic)
  → persist upload (S3) → create job → enqueue → worker submit/poll → result.
- **Payment:** checkout (amount quoted into payload) → gateway → signed/IP-checked
  webhook → `apply_event` (idempotent, amount-validated) → entitlement + notify.

## Scaling notes
- API: stateless → scale gunicorn workers / replicas behind Caddy.
- Workers: scale `worker` replicas; keep `beat` at 1.
- DB: front with PgBouncer (`DB_PGBOUNCER=true`) in transaction-pooling mode.
- Hot indexes: see `migrations/versions/0007_*` and `scripts/db_maintenance.sql`.
