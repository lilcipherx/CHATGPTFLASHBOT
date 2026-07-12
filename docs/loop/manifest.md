# Loop Engineering — reviewable-file manifest

592 tracked files @ `bb44014`. Status per area/file: `pending` | `reviewed` | `fixed` |
`n/a`. This manifest is maintained incrementally as each domain loop reviews its files —
Loop 0 sets the map and marks everything `pending` except what discovery already read.

Legend — Evidence: what proved the status (test name, command, code trace). Commit: SHA of
the verified change (or `—` for review-only).

## Domain areas and current status

| Area | Files | Loop 0 status | Owning domain loop |
|------|-------|---------------|--------------------|
| `core/payments/` (base, service, yookassa, stripe, crypto, tribute) | 6 | pending | L1 payments |
| `core/services/` billing/checkout/refunds/credits/pricing/packs/promos/loyalty/daily_bonus/referrals/gifts | ~11 | pending | L1 payments |
| `api/routers/webhooks.py` | 1 | reviewed (discovery) | L1 payments |
| `bot/handlers/premium.py, packs_buy.py, gift.py, promo.py` | 4 | reviewed (discovery) | L1 payments |
| `core/services/admin_auth.py, crypto.py`, `api/admin/auth.py`, `api/admin/deps.py`, `api/deps.py`, `core/config.py` | 6 | reviewed (C1/C3 dismissed fail-closed) | L2 auth/RBAC |
| `api/admin/*` routers (RBAC matrix) | ~24 | reviewed — all guarded (test_admin_rbac_coverage) | L2 auth/RBAC |
| `core/services/ai_routing.py, quota.py, gate.py, ratelimit.py, media_dispatch.py`, `core/ai_router/*` | ~20 | pending | L3 generation |
| `workers/*` (ARQ tasks + beat) | 16 | pending | L3 generation |
| `core/db.py`, `core/models/*`, `migrations/versions/*` | ~46 | reviewed head/drift only | L4 database |
| `api/routers/miniapp.py, gallery.py, images.py, carousel.py` | 4 | pending | L5 backend/API |
| `bot/handlers/*` (remaining), `bot/middlewares/*`, `bot/keyboards/*`, `bot/states/*` | ~40 | reviewed order/structure | L5 bot |
| `miniapp/src/*` (pages, components, api) | ~44 | pending (Playwright) | L6 Mini App |
| `admin/src/*` (pages, components, api) | ~57 | pending (Playwright) | L6 Admin |
| `Dockerfile`, `docker-compose*.yml`, `Caddyfile`, `.github/workflows/*`, `monitoring/*`, `scripts/*.sh` | ~20 | reviewed config only | L7 security/ops |
| `tests/*` | 155 | baseline green (905 passed) | all loops |

## Per-file detail

Per-file rows are appended by each domain loop as files are individually reviewed/fixed.
Format: `path | purpose | status | evidence | test | commit`.

### L0 discovery (reviewed at map level)
- `bot/main.py` | dispatcher + middleware/router wiring | reviewed | discovery trace | — | —
- `api/main.py` | FastAPI app, lifespan, SPA mounts | reviewed | discovery trace | — | —
- `workers/main.py` | ARQ WorkerSettings + BeatSettings + 15 cron | reviewed | discovery trace | — | —
- `core/db.py` | async engine sqlite/pgbouncer/pool modes | reviewed | discovery trace | — | —
- `api/routers/webhooks.py` | TG + gateway webhooks, dedup + idempotency | reviewed | discovery trace | — | —
- `migrations/versions/0042_search_model.py` | latest head | reviewed | `alembic heads` | check_migrations | —

_(appended per domain loop)_
